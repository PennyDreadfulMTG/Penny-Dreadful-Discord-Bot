from typing import List, Optional

from flask import Response, request, session, url_for

from decksite import APP, auth, league
from decksite.data import card as cs
from decksite.data import competition as comp
from decksite.data import deck, match
from decksite.data import person as ps
from decksite.views import DeckEmbed
from magic import oracle, rotation
from magic.models import Deck
from shared import configuration, dtutil, guarantee
from shared.pd_exception import DoesNotExistException, TooManyItemsException
from shared_web import template
from shared_web.api import generate_error, return_json, validate_api_key


@APP.route('/api/decks/<int:deck_id>/')
def deck_api(deck_id: int) -> Response:
    blob = deck.load_deck(deck_id)
    return return_json(blob)

@APP.route('/api/randomlegaldeck')
def random_deck_api() -> Response:
    blob = deck.random_legal_deck()
    if blob is None:
        return return_json({'error': True, 'msg': 'No legal decks could be found'})
    blob['url'] = url_for('deck', deck_id=blob['id'], _external=True)
    return return_json(blob)

@APP.route('/api/competitions/')
def competitions_api() -> Response:
    # Don't send competitions with any decks that do not have their correct archetype to third parties otherwise they
    # will store it and be wrong forever.
    comps = comp.load_competitions(having='num_reviewed = num_decks')
    r = []
    for c in comps:
        if c.decks:
            cr = {}
            cr['id'] = c.id
            cr['name'] = c.name
            cr['url'] = url_for('competition_api', competition_id=c.id, _external=True)
            r.append(cr)
    return return_json(r) # type: ignore

@APP.route('/api/competitions/<competition_id>')
def competition_api(competition_id: int) -> Response:
    return return_json(comp.load_competition(competition_id))

@APP.route('/api/league')
def league_api() -> Response:
    return return_json(league.active_league())

@APP.route('/api/person/<person>/')
def person_api(person: str) -> Response:
    try:
        p = ps.load_person_by_discord_id_or_username(person)
        p.decks_url = url_for('person_decks_api', person=person)
        p.head_to_head = url_for('person_h2h_api', person=person)
        return return_json(p)
    except DoesNotExistException:
        return return_json(generate_error('NOTFOUND', 'Person does not exist'))

@APP.route('/api/person/<person>/decks')
def person_decks_api(person: str) -> Response:
    p = ps.load_person_by_discord_id_or_username(person)
    blob = {
        'name': p.name,
        'decks': p.decks,
    }
    return return_json(blob)

@APP.route('/api/person/<person>/h2h')
def person_h2h_api(person: str) -> Response:
    p = ps.load_person_by_discord_id_or_username(person)
    return return_json(p.head_to_head)

@APP.route('/api/league/run/<person>')
def league_run_api(person: str) -> Response:
    decks = league.active_decks_by(person)
    if len(decks) == 0:
        return return_json(None)

    run = guarantee_at_most_one_or_retire(decks)
    if run is None:
        return return_json(None)

    decks = league.active_decks()
    already_played = [m.opponent_deck_id for m in match.get_matches(run)]
    run.can_play = [d.person for d in decks if d.person != person and d.id not in already_played]

    return return_json(run)

@APP.route('/api/league/drop/<person>', methods=['POST'])
def drop(person):
    error = validate_api_key()
    if error:
        return error

    decks = league.active_decks_by(person)
    if len(decks) == 0:
        return return_json(generate_error('NO_ACTIVE_RUN', 'That person does not have an active run'))

    run = guarantee.exactly_one(decks)

    league.retire_deck(run)
    result = {'success':True}
    return return_json(result)

@APP.route('/api/rotation')
def rotation_api() -> Response:
    now = dtutil.now()
    diff = rotation.next_rotation() - now
    result = {
        'last': rotation.last_rotation_ex(),
        'next': rotation.next_rotation_ex(),
        'diff': diff.total_seconds(),
        'friendly_diff': dtutil.display_time(diff.total_seconds())
    }
    return return_json(result)

@APP.route('/api/cards')
def cards_api() -> Response:
    blob = {'cards': cs.load_cards()}
    return return_json(blob)

@APP.route('/api/card/<card>')
def card_api(card: str) -> Response:
    return return_json(oracle.load_card(card))

@APP.route('/api/sitemap/')
def sitemap() -> Response:
    urls = [url_for(rule.endpoint) for rule in APP.url_map.iter_rules() if 'GET' in rule.methods and len(rule.arguments) == 0]
    return return_json({'urls': urls})

@APP.route('/api/intro/')
def intro() -> Response:
    return return_json(not request.cookies.get('hide_intro', False) and not auth.hide_intro())

@APP.route('/api/intro/', methods=['POST'])
def hide_intro() -> Response:
    r = Response(response='')
    r.set_cookie('hide_intro', value=str(True), expires=dtutil.dt2ts(dtutil.now()) + 60 *  60 * 24 * 365 * 10)
    return r

@APP.route('/api/status/')
@auth.load_person
def person_status() -> Response:
    username = auth.mtgo_username()
    r = {
        'mtgo_username': username,
        'discord_id': auth.discord_id(),
        'admin': session.get('admin', False),
        'demimod': session.get('demimod', False),
        'hide_intro': request.cookies.get('hide_intro', False) or auth.hide_intro() or username or auth.discord_id(),
        'in_guild': session.get('in_guild', False),
        }
    if username:
        d = guarantee_at_most_one_or_retire(league.active_decks_by(username))
        if d is not None:
            r['deck'] = {'name': d.name, 'url': url_for('deck', deck_id=d.id), 'wins': d.get('wins', 0), 'losses': d.get('losses', 0)}
    if r['admin'] or r['demimod']:
        r['archetypes_to_tag'] = len(deck.load_decks('NOT d.reviewed'))
    return return_json(r)

def guarantee_at_most_one_or_retire(decks: List[Deck]) -> Optional[Deck]:
    try:
        run = guarantee.at_most_one(decks)
    except TooManyItemsException:
        league.retire_deck(decks[0])
        run = decks[1]
    return run

@APP.route('/decks/<deck_id>/oembed')
def deck_embed(deck_id):
    # Discord doesn't actually show this yet.  I've reached out to them for better documentation about what they do/don't accept.
    d = deck.load_deck(deck_id)
    view = DeckEmbed(d, None, None)
    width = 1200
    height = 500
    embed = {
        'type': 'rich',
        'version': '1.0',
        'title': view.page_title(),
        'width': width,
        'height': height,
        'html': template.render(view)
    }
    return return_json(embed)

@APP.route('/api/test_500')
def test_500() -> Response:
    if configuration.get_bool('production'):
        return return_json(generate_error('ON_PROD', 'This only works on test environments'), status=404)
    raise TooManyItemsException()
