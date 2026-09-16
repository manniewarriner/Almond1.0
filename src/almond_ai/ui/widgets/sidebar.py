import re

from textual.message import Message
from textual.widgets import Label


def navigation_id(name: str) -> str:
    return "nav-" + re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


class NavItem(Label):
    """Clickable nav row. Selecting it posts its name for the App to route.

    Used both by `BotSidebar`'s "Settings" entry and by the Developer
    section inside `SettingsView` for the technical views (Tools, Data &
    RAG, Integrations, Evaluation, Logs, Deploy, Permissions) -- any
    NavItem mounted anywhere under the App bubbles `Selected` up to
    `AlmondDeveloperApp.navigate`.
    """

    class Selected(Message):
        def __init__(self, name: str) -> None:
            self.name = name
            super().__init__()

    def __init__(self, name: str) -> None:
        super().__init__(name, classes="nav-item", id=navigation_id(name))
        self.nav_name = name

    def on_click(self) -> None:
        self.post_message(self.Selected(self.nav_name))
