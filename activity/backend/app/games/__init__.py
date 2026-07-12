"""Single-player word games for the Hablemos Activity.

Each game implements :class:`app.games.base.GameEngine` and is registered in
:mod:`app.games.registry`. Wordle is the first; adding another game requires
no changes outside its own module + one registry line.
"""
