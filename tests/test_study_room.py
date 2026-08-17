import unittest
from io import BytesIO
from pathlib import Path

from PIL import Image
from streamlit.testing.v1 import AppTest

from models.shop import StudyRoomEquipment
from services.shop_repository import (
    get_user_study_room,
    save_user_study_room,
)
from services.study_room_service import (
    ROOM_CANVAS_SIZE,
    compose_study_room_preview,
    validate_study_room_equipment,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
USER_ID = "00000000-0000-0000-0000-000000000001"
NOW = "2026-08-17T10:00:00+00:00"


class FakeResponse:
    def __init__(self, data):
        self.data = data


class FakeRequest:
    def __init__(self, data):
        self.data = data
        self.filters = []

    def select(self, _fields):
        return self

    def eq(self, field, value):
        self.filters.append((field, value))
        return self

    def maybe_single(self):
        return self

    def execute(self):
        if self.data is None:
            return None
        return FakeResponse(self.data)


class FakeSupabase:
    def __init__(self, room=None):
        self.room = room
        self.table_requests = []
        self.rpc_calls = []

    def table(self, table_name):
        self.assert_table_name = table_name
        request = FakeRequest(self.room)
        self.table_requests.append((table_name, request))
        return request

    def rpc(self, function_name, params):
        self.rpc_calls.append((function_name, params))
        return FakeRequest(
            {
                "user_id": USER_ID,
                **{
                    key.removeprefix("p_"): value
                    for key, value in params.items()
                },
                "created_at": NOW,
                "updated_at": NOW,
            }
        )


def render_study_room_test_page(supabase):
    from services.shop_catalog import SHOP_ITEM_CATALOG
    from views.study_room_view import render_study_room

    test_user_id = "00000000-0000-0000-0000-000000000001"
    test_now = "2026-08-17T10:00:00+00:00"
    owned_keys = {
        "desk_oak_basic",
        "decor_green_plant",
        "decor_focus_lamp",
    }
    items = [
        item.model_dump(mode="json")
        for item in SHOP_ITEM_CATALOG
    ]
    inventory = [
        {
            "user_id": test_user_id,
            "item_key": item_key,
            "purchase_transaction_id": (
                f"00000000-0000-0000-0000-{index:012d}"
            ),
            "price_paid": 30,
            "acquired_at": test_now,
        }
        for index, item_key in enumerate(sorted(owned_keys), start=10)
    ]
    render_study_room(
        supabase,
        {"items": items, "inventory": inventory},
        saved_room=None,
    )


class StudyRoomModelAndServiceTests(unittest.TestCase):
    def test_same_decoration_cannot_fill_both_slots(self):
        with self.assertRaises(ValueError):
            StudyRoomEquipment(
                decor_left_item_key="decor_green_plant",
                decor_right_item_key="decor_green_plant",
            )

    def test_validation_requires_ownership_and_slot_compatibility(self):
        with self.assertRaisesRegex(ValueError, "보유하지 않은"):
            validate_study_room_equipment(
                {"desk_item_key": "desk_oak_basic"},
                owned_item_keys=set(),
            )

        with self.assertRaisesRegex(ValueError, "해당 학습방 슬롯"):
            validate_study_room_equipment(
                {"chair_item_key": "desk_oak_basic"},
                owned_item_keys={"desk_oak_basic"},
            )

    def test_preview_composes_owned_items_at_room_canvas_size(self):
        equipment = {
            "background_item_key": "wall_warm_cream",
            "desk_item_key": "desk_oak_basic",
            "decor_left_item_key": "decor_green_plant",
            "decor_right_item_key": "decor_focus_lamp",
        }
        preview = compose_study_room_preview(
            equipment,
            owned_item_keys=set(value for value in equipment.values()),
        )

        with Image.open(BytesIO(preview)) as image:
            self.assertEqual(image.size, ROOM_CANVAS_SIZE)
            self.assertEqual(image.format, "WEBP")


class StudyRoomRepositoryTests(unittest.TestCase):
    def test_missing_room_is_a_normal_empty_result(self):
        supabase = FakeSupabase(room=None)

        result = get_user_study_room(supabase, USER_ID)

        self.assertIsNone(result)
        table_name, request = supabase.table_requests[0]
        self.assertEqual(table_name, "user_study_rooms")
        self.assertEqual(request.filters, [("user_id", USER_ID)])

    def test_room_read_filters_authenticated_user_id(self):
        room = {
            "user_id": USER_ID,
            "background_item_key": None,
            "floor_item_key": None,
            "desk_item_key": None,
            "chair_item_key": None,
            "decor_left_item_key": None,
            "decor_right_item_key": None,
            "accent_item_key": None,
            "created_at": NOW,
            "updated_at": NOW,
        }
        supabase = FakeSupabase(room=room)

        result = get_user_study_room(supabase, USER_ID)

        self.assertEqual(result["user_id"], USER_ID)
        table_name, request = supabase.table_requests[0]
        self.assertEqual(table_name, "user_study_rooms")
        self.assertEqual(request.filters, [("user_id", USER_ID)])

    def test_room_save_sends_only_seven_slot_values(self):
        supabase = FakeSupabase()
        equipment = {
            "background_item_key": None,
            "floor_item_key": None,
            "desk_item_key": "desk_oak_basic",
            "chair_item_key": None,
            "decor_left_item_key": None,
            "decor_right_item_key": None,
            "accent_item_key": None,
        }

        result = save_user_study_room(supabase, equipment)

        self.assertEqual(result["desk_item_key"], "desk_oak_basic")
        self.assertEqual(len(supabase.rpc_calls), 1)
        function_name, params = supabase.rpc_calls[0]
        self.assertEqual(function_name, "save_user_study_room")
        self.assertEqual(
            set(params),
            {
                "p_background_item_key",
                "p_floor_item_key",
                "p_desk_item_key",
                "p_chair_item_key",
                "p_decor_left_item_key",
                "p_decor_right_item_key",
                "p_accent_item_key",
            },
        )


class StudyRoomViewTests(unittest.TestCase):
    def test_preview_changes_do_not_save_until_button_is_pressed(self):
        supabase = FakeSupabase()
        app = AppTest.from_function(
            render_study_room_test_page,
            args=(supabase,),
        ).run()

        self.assertEqual(list(app.exception), [])
        save_button = next(
            button for button in app.button
            if button.label == "학습방 저장하기"
        )
        self.assertTrue(save_button.disabled)
        self.assertEqual(supabase.rpc_calls, [])

        desk_selector = next(
            selector for selector in app.selectbox
            if selector.label == "책상"
        )
        app = desk_selector.set_value("desk_oak_basic").run()

        self.assertEqual(supabase.rpc_calls, [])
        save_button = next(
            button for button in app.button
            if button.label == "학습방 저장하기"
        )
        self.assertFalse(save_button.disabled)

        app = save_button.click().run()

        self.assertEqual(list(app.exception), [])
        self.assertEqual(len(supabase.rpc_calls), 1)
        self.assertEqual(supabase.rpc_calls[0][0], "save_user_study_room")


class StudyRoomMigrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema_sql = (
            PROJECT_ROOT / "supabase_study_rooms.sql"
        ).read_text(encoding="utf-8").lower()
        cls.validation_sql = (
            PROJECT_ROOT / "supabase_study_rooms_validation.sql"
        ).read_text(encoding="utf-8").lower()

    def test_schema_uses_rls_and_server_only_writes(self):
        self.assertIn(
            "alter table public.user_study_rooms enable row level security",
            self.schema_sql,
        )
        self.assertIn("auth.uid()", self.schema_sql)
        self.assertIn(
            "revoke all on public.user_study_rooms from anon, authenticated",
            self.schema_sql,
        )
        self.assertNotIn(
            "grant insert on public.user_study_rooms to authenticated",
            self.schema_sql,
        )

    def test_save_rpc_validates_inventory_slots_and_duplicate_decor(self):
        self.assertIn("security definer", self.schema_sql)
        self.assertIn("set search_path = ''", self.schema_sql)
        self.assertIn("public.user_inventory", self.schema_sql)
        self.assertIn("item.allowed_slots", self.schema_sql)
        self.assertIn(
            "decor_left_item_key <> decor_right_item_key",
            self.schema_sql,
        )
        self.assertIn("set transaction read only", self.validation_sql)


if __name__ == "__main__":
    unittest.main()
