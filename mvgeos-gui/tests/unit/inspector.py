import pytest
from nicegui import ui
from nicegui.testing import User

from mvgeos_gui.components.inspector import _render_background_task_row
from mvgeos_gui.models import BackgroundTask, TaskStatus


@pytest.mark.asyncio
async def test_render_background_task_running(user: User) -> None:
    task = BackgroundTask(id="t1", name="bash", status=TaskStatus.RUNNING, progress=0.5)

    @ui.page("/test_inspector_running")
    def page() -> None:
        _render_background_task_row(task)

    await user.open("/test_inspector_running")
    await user.should_see("bash")


@pytest.mark.asyncio
async def test_render_background_task_complete(user: User) -> None:
    task = BackgroundTask(
        id="t2", name="review", status=TaskStatus.COMPLETE, progress=1.0
    )

    @ui.page("/test_inspector_complete")
    def page() -> None:
        _render_background_task_row(task)

    await user.open("/test_inspector_complete")
    await user.should_see("review")


@pytest.mark.asyncio
async def test_render_background_task_error(user: User) -> None:
    task = BackgroundTask(
        id="t3", name="failing", status=TaskStatus.ERROR, progress=0.2
    )

    @ui.page("/test_inspector_error")
    def page() -> None:
        _render_background_task_row(task)

    await user.open("/test_inspector_error")
    await user.should_see("failing")
