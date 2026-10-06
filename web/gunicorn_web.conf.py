"""Keep preloaded database connections out of forked web workers."""


def _reset_database_pool(app, *, close):
    from db import db

    with app.app_context():
        db.session.remove()
        for engine in db.engines.values():
            engine.dispose(close=close)


def pre_fork(server, worker):
    # WSGI starts no background threads, so all master connections are idle.
    # Close them in their owning process before any descriptors are inherited.
    _reset_database_pool(server.app.wsgi(), close=True)


def post_fork(server, worker):
    # Each child gets its own pool; never close another process's connections.
    _reset_database_pool(server.app.wsgi(), close=False)
