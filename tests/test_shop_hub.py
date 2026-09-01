import unittest
from types import SimpleNamespace
from unittest.mock import ANY, Mock, patch

from streamlit.testing.v1 import AppTest

from views.shop_pages_view import (
    SHOP_HUB_SECTION_COLLECTION,
    SHOP_HUB_SECTION_ROOM,
    normalize_shop_hub_section,
    render_study_room_page,
)


USER = SimpleNamespace(id="00000000-0000-4000-8000-000000000001")
SHOP_DATA = {"wallet": {}, "items": [], "inventory": []}


def render_shop_hub_navigation_test_page() -> None:
    import streamlit as st
    from views.shop_pages_view import _render_shop_hub_navigation

    st.write(_render_shop_hub_navigation())


class ShopHubTests(unittest.TestCase):
    def test_navigation_defaults_to_room_without_widget_warning(self):
        app = AppTest.from_function(render_shop_hub_navigation_test_page).run()

        self.assertEqual(list(app.exception), [])
        self.assertEqual(app.segmented_control[0].value, SHOP_HUB_SECTION_ROOM)
        self.assertEqual(len(app.segmented_control[0].options), 2)
        self.assertEqual(app.markdown[-1].value, SHOP_HUB_SECTION_ROOM)

    def test_section_normalization_rejects_unknown_values(self):
        self.assertEqual(
            normalize_shop_hub_section(SHOP_HUB_SECTION_COLLECTION),
            SHOP_HUB_SECTION_COLLECTION,
        )
        self.assertEqual(normalize_shop_hub_section("unknown"), "room")
        self.assertEqual(normalize_shop_hub_section("inventory"), "room")
        self.assertEqual(normalize_shop_hub_section(None), "room")

    def test_room_and_collection_reuse_one_room_load(self):
        for section in (
            SHOP_HUB_SECTION_ROOM,
            SHOP_HUB_SECTION_COLLECTION,
        ):
            with self.subTest(section=section):
                saved_room = {"user_id": USER.id}
                with (
                    patch("views.shop_pages_view.render_page_header"),
                    patch(
                        "views.shop_pages_view._render_shop_hub_navigation",
                        return_value=section,
                    ),
                    patch(
                        "views.shop_pages_view._load_shop_data",
                        return_value=SHOP_DATA,
                    ) as load_shop,
                    patch(
                        "views.shop_pages_view.load_study_room_data",
                        return_value=saved_room,
                    ) as load_room,
                    patch("views.shop_pages_view.render_study_room") as render_room,
                    patch(
                        "views.shop_pages_view.render_shop_collection"
                    ) as render_collection,
                ):
                    render_study_room_page(
                        Mock(),
                        USER,
                        profile={"level": 1, "current_streak": 0},
                    )

                load_shop.assert_called_once()
                load_room.assert_called_once_with(ANY, USER.id)
                if section == SHOP_HUB_SECTION_ROOM:
                    render_room.assert_called_once()
                    render_collection.assert_not_called()
                else:
                    render_collection.assert_called_once_with(
                        SHOP_DATA,
                        saved_room,
                    )
                    render_room.assert_not_called()


if __name__ == "__main__":
    unittest.main()
