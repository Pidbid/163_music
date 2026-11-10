from nm_shell.window_manager import fit_bounds

SCREEN = (0, 0, 1280, 800)  # a 2560x1600 panel at scale 2
MINIMUM = (940, 620)


def test_window_wider_than_the_screen_is_shrunk_and_centred() -> None:
    fitted = fit_bounds((0, 0, 1380, 880), SCREEN, MINIMUM)
    assert fitted is not None
    x, y, width, height = fitted
    assert width == 1280 - 48
    assert height == 800 - 48
    assert x == 24 and y == 24


def test_a_window_that_already_fits_is_left_alone() -> None:
    assert fit_bounds((100, 80, 960, 700), SCREEN, MINIMUM) is None


def test_a_window_off_the_work_area_is_recentred() -> None:
    fitted = fit_bounds((1200, 700, 960, 700), SCREEN, MINIMUM)
    assert fitted is not None
    x, y, width, height = fitted
    assert (width, height) == (960, 700)
    assert 0 <= x and x + width <= 1280
    assert 0 <= y and y + height <= 800


def test_the_minimum_size_is_never_violated() -> None:
    fitted = fit_bounds((0, 0, 400, 300), SCREEN, MINIMUM)
    assert fitted is not None
    _, _, width, height = fitted
    assert (width, height) == MINIMUM


def test_a_screen_smaller_than_the_minimum_size_degrades_to_the_minimum() -> None:
    fitted = fit_bounds((0, 0, 800, 600), (0, 0, 700, 500), MINIMUM)
    assert fitted is not None
    _, _, width, height = fitted
    assert (width, height) == MINIMUM


def test_a_secondary_screen_offsets_the_work_area() -> None:
    fitted = fit_bounds((1400, 0, 1380, 880), (1280, 0, 1280, 800), MINIMUM)
    assert fitted is not None
    x, y, width, height = fitted
    assert x == 1280 + 24
    assert y == 24
    assert x + width <= 2560
