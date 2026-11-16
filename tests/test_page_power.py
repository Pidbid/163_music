from nm_shell.page_power import ACTIVE, SUSPENDED, SuspendPolicy, may_suspend


def test_a_playing_page_is_never_suspended() -> None:
    # The audio element lives in the page: dropping it would cut the music.
    assert not may_suspend(hidden=True, playing=True, audible=False)
    assert not may_suspend(hidden=True, playing=False, audible=True)


def test_a_visible_page_is_never_suspended() -> None:
    assert not may_suspend(hidden=False, playing=False, audible=False)


def test_a_hidden_silent_page_is_suspended_once_per_hiding() -> None:
    assert may_suspend(hidden=True, playing=False, audible=False, armed=True)
    assert not may_suspend(hidden=True, playing=False, audible=False, armed=False)


def test_hiding_arms_the_policy_and_showing_disarms_it() -> None:
    policy = SuspendPolicy()
    policy.set_hidden(True)
    assert policy.armed is True
    assert policy.needs_suspend() is True
    policy.set_hidden(False)
    assert policy.armed is False
    assert policy.needs_suspend() is False


def test_playback_starting_in_the_tray_disarms_the_policy() -> None:
    policy = SuspendPolicy()
    policy.set_hidden(True)
    policy.set_playing(True)
    assert policy.needs_suspend() is False
    # ... and pausing again must not put the page the user drives back to sleep.
    policy.set_playing(False)
    assert policy.needs_suspend() is False


def test_engine_audibility_holds_the_page_open() -> None:
    policy = SuspendPolicy()
    policy.set_hidden(True)
    policy.set_audible(True)
    assert policy.needs_suspend() is False
    policy.set_audible(False)
    assert policy.needs_suspend() is True


def test_suspending_disarms_until_the_next_hide() -> None:
    policy = SuspendPolicy()
    policy.set_hidden(True)
    assert policy.needs_suspend() is True
    policy.disarm()
    assert policy.needs_suspend() is False
    policy.set_hidden(True)
    assert policy.needs_suspend() is True


def test_the_states_are_plain_strings() -> None:
    assert (ACTIVE, SUSPENDED) == ("active", "suspended")
