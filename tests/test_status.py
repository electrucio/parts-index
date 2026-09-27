from parts_index.status import model_next


def test_a_note_is_not_a_pending_step():
    entry = {"status": "active", "fetch": "manual", "note": "HTTrack mirror of the old vendor tree."}
    assert model_next(entry, files=4302, not_tried=0) == "up to date"


def test_a_source_with_nothing_downloaded_says_so():
    assert model_next({"status": "active", "fetch": "manual"}, files=0, not_tried=0) == "nothing downloaded"


def test_parts_left_to_ask_for_come_before_anything_else_that_is_left():
    assert model_next({"status": "active", "fetch": "adapter"}, files=10, not_tried=45) == "fetch 45 parts"


def test_models_installed_with_a_simulator_have_nothing_to_download():
    assert model_next({"status": "active", "fetch": "installed"}, files=0, not_tried=0) == "ships with the simulator"


def test_manual_sources_keep_their_own_wording():
    assert model_next({"status": "link_only"}, files=0, not_tried=0) == "manual: link only"
    assert model_next({"status": "pending_manual"}, files=0, not_tried=0) == "manual download"
