from decksite.view import View


# pylint: disable=no-self-use
class Unauthorized(View):
    def __init__(self, error):
        super().__init__()
        if error:
            self.error = error

    def subtitle(self):
        return 'Unauthorized'
