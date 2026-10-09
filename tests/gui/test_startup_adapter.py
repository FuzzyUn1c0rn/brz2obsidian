"""Public startup lifecycle controls; no native windows or real user endpoints."""

from threading import Event


def test_coordination_is_off_caller_thread_and_only_owner_requests_window(tmp_path):
    from brz2obsidian_ui.instance import InstanceResult
    from brz2obsidian_ui.startup import StartupCoordinator

    blocked, release, primary = Event(), Event(), Event()

    class Instance:
        def claim(self):
            blocked.set()
            assert release.wait(5)
            return InstanceResult("primary")

        def close(self):
            pass

    startup = StartupCoordinator(
        tmp_path,
        primary.set,
        lambda result: None,
        lambda result: None,
        instance_factory=lambda root, callback: Instance(),
    )
    try:
        startup.begin()
        assert blocked.wait(2)
        assert not primary.is_set()
        release.set()
        assert primary.wait(2)
    finally:
        release.set()
        startup.shutdown()


def test_second_launch_exits_without_requesting_a_window(tmp_path):
    from brz2obsidian_ui.instance import InstanceResult
    from brz2obsidian_ui.startup import StartupCoordinator

    completed = Event()
    windows, results = [], []

    class Existing:
        def claim(self):
            return InstanceResult("activation_requested")

        def close(self):
            pass

    def exiting(result):
        results.append(result.status)
        completed.set()

    startup = StartupCoordinator(
        tmp_path,
        lambda: windows.append("window"),
        exiting,
        lambda result: None,
        instance_factory=lambda root, callback: Existing(),
    )
    try:
        startup.begin()
        assert completed.wait(2)
        assert results == ["activation_requested"]
        assert windows == []
    finally:
        startup.shutdown()


def test_activation_arriving_before_window_readiness_is_delivered_after_ready(tmp_path):
    from brz2obsidian_ui.instance import InstanceResult
    from brz2obsidian_ui.startup import StartupCoordinator

    primary, delivered = Event(), Event()
    requests, activated = [], []

    class Owner:
        def __init__(self, root, callback):
            requests.append(callback)

        def claim(self):
            return InstanceResult("primary")

        def close(self):
            pass

    class Activator:
        def activate(self, hwnd):
            activated.append(hwnd)
            delivered.set()
            return InstanceResult("activated")

    startup = StartupCoordinator(
        tmp_path,
        primary.set,
        lambda result: None,
        lambda result: None,
        instance_factory=Owner,
        activator_factory=Activator,
    )
    try:
        startup.begin()
        assert primary.wait(2)
        requests[0]()
        startup.window_ready(42)
        assert delivered.wait(2)
        assert activated == [42]
    finally:
        startup.shutdown()
