import unittest

from services.shop_catalog import SHOP_ITEM_CATALOG
from views import collection_gallery_component
from views.collection_gallery_component import (
    build_collection_gallery_items,
)


def _catalog_items() -> list[dict]:
    return [item.model_dump(mode="json") for item in SHOP_ITEM_CATALOG]


class CollectionGalleryTests(unittest.TestCase):
    def test_builds_equipped_owned_and_locked_states(self):
        items = _catalog_items()[:3]
        nodes = build_collection_gallery_items(
            items,
            owned_keys={items[0]["item_key"], items[1]["item_key"]},
            equipped_keys={items[0]["item_key"]},
        )

        self.assertEqual(
            [node["status"] for node in nodes],
            ["equipped", "owned", "locked"],
        )
        self.assertEqual(
            [node["status_label"] for node in nodes],
            ["장착 중", "수집 완료", "미수집"],
        )

    def test_approved_local_thumbnail_is_encoded_as_data_url(self):
        item = _catalog_items()[0]

        node = build_collection_gallery_items(
            [item],
            owned_keys=set(),
            equipped_keys=set(),
        )[0]

        self.assertIsInstance(node["thumbnail"], str)
        self.assertTrue(node["thumbnail"].startswith("data:image/webp;base64,"))

    def test_unapproved_thumbnail_path_is_not_read(self):
        item = _catalog_items()[0]
        item["thumbnail_path"] = "../secret.txt"

        node = build_collection_gallery_items(
            [item],
            owned_keys=set(),
            equipped_keys=set(),
        )[0]

        self.assertIsNone(node["thumbnail"])

    def test_equipped_item_must_be_owned(self):
        item = _catalog_items()[0]

        with self.assertRaisesRegex(ValueError, "보유 정보"):
            build_collection_gallery_items(
                [item],
                owned_keys=set(),
                equipped_keys={item["item_key"]},
            )

    def test_card_selection_does_not_emit_streamlit_state(self):
        source = collection_gallery_component._GALLERY_JS

        self.assertIn("card.onclick = () => selectItem(item)", source)
        self.assertNotIn("setStateValue", source)
        self.assertNotIn("setTriggerValue", source)
        self.assertNotIn("Streamlit.setComponentValue", source)
        self.assertNotIn("window.parent.postMessage", source)


if __name__ == "__main__":
    unittest.main()
