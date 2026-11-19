"""Exercise the host's hide/idle/show path without a desktop or network."""

import pytest

import main


@pytest.mark.parametrize("tray_available", [True, False])
def test_hidden_idle_player_keeps_its_session(monkeypatch, tray_available):
    events = []
    timers = []

    class Process:
        pid = 123

        def is_alive(self):
            return True

        def join(self, timeout=None):
            pass

    class Session:
        def __init__(self, *args, **kwargs):
            self.process = Process()

        def ensure_running(self):
            return False

        def send(self, command):
            events.append(command)
            return True

        def retire(self):
            events.append("retired")

    class Timer:
        def __init__(self, delay, callback):
            self.callback = callback
            timers.append(self)

        def start(self):
            pass

        def cancel(self):
            pass

    class Tray:
        def __init__(self, send, on_quit, on_activity=None):
            self.send = send
            self.activity = on_activity

        def set_state_queue(self, queue):
            pass

        def run(self):
            self.send(main.HIDE_MAIN)
            if self.activity:
                self.activity(True, False, False)
            # Expire any idle deadline: the page must still be retained.
            for timer in list(timers):
                timer.callback()
            assert "retired" not in events
            self.send(main.SHOW_MAIN)
            self.send("player_toggle")
            assert events == [main.HIDE_MAIN, main.SHOW_MAIN, "player_toggle"]
            return tray_available

    class Instance:
        def start_server(self, callback):
            pass

    monkeypatch.setattr(main, "ChildSession", Session)
    monkeypatch.setattr(main, "TrayHost", Tray)
    monkeypatch.setattr(main.threading, "Timer", Timer)
    monkeypatch.setattr(main.threading.Thread, "start", lambda self: None)
    assert main._start_tray({}, Instance()) == 0
    last_command = main.QUIT if tray_available else main.TRAY_UNAVAILABLE
    assert events[-2:] == [last_command, "retired"]
