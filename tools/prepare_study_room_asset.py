import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageOps


CANVAS_SIZE = (1600, 900)
THUMBNAIL_SIZE = (256, 256)
LARGE_OVERLAY_COLOR_BITS = 6
WALL_POLYGONS = (
    ((132, 198), (800, 24), (800, 394), (140, 603)),
    ((800, 24), (1495, 198), (1495, 603), (800, 394)),
)
FLOOR_POLYGON = (
    (140, 603),
    (800, 394),
    (1495, 603),
    (800, 876),
)


def prepare_scene(
    source_path: Path,
    output_path: Path,
    thumbnail_path: Path | None = None,
) -> None:
    """전체 방 이미지를 고정 캔버스와 선택 썸네일로 변환합니다."""

    with Image.open(source_path) as source:
        scene = ImageOps.fit(
            source.convert("RGB"),
            CANVAS_SIZE,
            method=Image.Resampling.LANCZOS,
        )
        _save_image(scene, output_path)
        if thumbnail_path is not None:
            thumbnail = ImageOps.fit(
                scene,
                THUMBNAIL_SIZE,
                method=Image.Resampling.LANCZOS,
            )
            _save_image(thumbnail, thumbnail_path)


def prepare_overlay(
    source_path: Path,
    output_path: Path,
    thumbnail_path: Path,
    *,
    target_width: int,
    left: int,
    top: int,
) -> None:
    """투명 오브젝트를 고정 좌표의 전체 캔버스 오버레이로 만듭니다."""

    if target_width <= 0 or target_width > CANVAS_SIZE[0]:
        raise ValueError("오버레이 너비가 캔버스 범위를 벗어났습니다.")

    with Image.open(source_path) as source:
        cutout = source.convert("RGBA")
        alpha_box = cutout.getchannel("A").getbbox()
        if alpha_box is None:
            raise ValueError("투명 오브젝트에서 유효한 픽셀을 찾지 못했습니다.")
        cutout = cutout.crop(alpha_box)

        target_height = round(cutout.height * target_width / cutout.width)
        cutout = cutout.resize(
            (target_width, target_height),
            Image.Resampling.LANCZOS,
        )
        if (
            left < 0
            or top < 0
            or left + target_width > CANVAS_SIZE[0]
            or top + target_height > CANVAS_SIZE[1]
        ):
            raise ValueError("오버레이 배치 좌표가 캔버스 범위를 벗어났습니다.")

        canvas = Image.new("RGBA", CANVAS_SIZE, (0, 0, 0, 0))
        canvas.alpha_composite(cutout, (left, top))
        _save_image(canvas, output_path)

        thumbnail = Image.new("RGBA", THUMBNAIL_SIZE, (0, 0, 0, 0))
        thumb_object = ImageOps.contain(
            cutout,
            (224, 224),
            method=Image.Resampling.LANCZOS,
        )
        thumb_left = (THUMBNAIL_SIZE[0] - thumb_object.width) // 2
        thumb_top = (THUMBNAIL_SIZE[1] - thumb_object.height) // 2
        thumbnail.alpha_composite(thumb_object, (thumb_left, thumb_top))
        _save_image(thumbnail, thumbnail_path)


def prepare_background_overlay(
    base_source_path: Path,
    variant_source_path: Path,
    output_path: Path,
    thumbnail_path: Path,
) -> None:
    """고정 방 시점의 두 벽만 교체하는 투명 배경 오버레이를 만듭니다."""

    with Image.open(base_source_path) as base_source:
        base = ImageOps.fit(
            base_source.convert("RGB"),
            CANVAS_SIZE,
            method=Image.Resampling.LANCZOS,
        )
    with Image.open(variant_source_path) as variant_source:
        variant = ImageOps.fit(
            variant_source.convert("RGBA"),
            CANVAS_SIZE,
            method=Image.Resampling.LANCZOS,
        )

    mask = Image.new("L", CANVAS_SIZE, 0)
    mask_draw = ImageDraw.Draw(mask)
    for polygon in WALL_POLYGONS:
        mask_draw.polygon(polygon, fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(radius=1.25))
    variant.putalpha(mask)
    _save_image(optimize_large_overlay(variant), output_path)

    preview = base.convert("RGBA")
    preview.alpha_composite(variant)
    thumbnail = ImageOps.fit(
        preview.convert("RGB"),
        THUMBNAIL_SIZE,
        method=Image.Resampling.LANCZOS,
    )
    _save_image(thumbnail, thumbnail_path)


def prepare_floor_overlay(
    base_source_path: Path,
    variant_source_path: Path,
    output_path: Path,
    thumbnail_path: Path,
) -> None:
    """고정 방 시점의 안쪽 바닥만 교체하는 투명 오버레이를 만듭니다."""

    with Image.open(base_source_path) as base_source:
        base = ImageOps.fit(
            base_source.convert("RGB"),
            CANVAS_SIZE,
            method=Image.Resampling.LANCZOS,
        )
    with Image.open(variant_source_path) as variant_source:
        variant = ImageOps.fit(
            variant_source.convert("RGBA"),
            CANVAS_SIZE,
            method=Image.Resampling.LANCZOS,
        )

    mask = Image.new("L", CANVAS_SIZE, 0)
    ImageDraw.Draw(mask).polygon(FLOOR_POLYGON, fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(radius=1.25))
    variant.putalpha(mask)
    _save_image(optimize_large_overlay(variant), output_path)

    preview = base.convert("RGBA")
    preview.alpha_composite(variant)
    thumbnail = ImageOps.fit(
        preview.convert("RGB"),
        THUMBNAIL_SIZE,
        method=Image.Resampling.LANCZOS,
    )
    _save_image(thumbnail, thumbnail_path)


def build_preview(
    base_path: Path,
    overlay_paths: list[Path],
    output_path: Path,
) -> None:
    """기본 방과 오버레이를 순서대로 합성한 검수 이미지를 만듭니다."""

    with Image.open(base_path) as base_source:
        preview = base_source.convert("RGBA")
    if preview.size != CANVAS_SIZE:
        raise ValueError("기본 방 이미지 규격이 1600×900이 아닙니다.")

    for overlay_path in overlay_paths:
        with Image.open(overlay_path) as overlay_source:
            overlay = overlay_source.convert("RGBA")
        if overlay.size != CANVAS_SIZE:
            raise ValueError("오버레이 이미지 규격이 1600×900이 아닙니다.")
        preview.alpha_composite(overlay)

    _save_image(preview.convert("RGB"), output_path)


def optimize_large_overlay(image: Image.Image) -> Image.Image:
    """큰 투명 오버레이의 RGB 단계만 줄이고 알파 마스크는 보존합니다."""

    rgba = image.convert("RGBA")
    alpha = rgba.getchannel("A")
    optimized = ImageOps.posterize(
        rgba.convert("RGB"),
        LARGE_OVERLAY_COLOR_BITS,
    )
    optimized.putalpha(alpha)
    return optimized


def export_catalog(output_path: Path) -> None:
    """Python 상점 카탈로그를 사람이 수정 가능한 JSON으로 내보냅니다."""

    from services.shop_catalog import SHOP_ITEM_CATALOG

    payload = [
        item.model_dump(mode="json")
        for item in SHOP_ITEM_CATALOG
    ]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _save_image(image: Image.Image, output_path: Path) -> None:
    """확장자별 고정 옵션으로 이미지 파일을 저장합니다."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    suffix = output_path.suffix.lower()
    if suffix == ".png":
        image.save(output_path, format="PNG", optimize=True)
        return
    if suffix == ".webp":
        image.save(
            output_path,
            format="WEBP",
            quality=90,
            method=6,
        )
        return
    raise ValueError("지원하는 출력 형식은 PNG와 WebP입니다.")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="학습방 생성 원본을 프로젝트 에셋 규격으로 변환합니다."
    )
    commands = parser.add_subparsers(dest="command", required=True)

    scene = commands.add_parser("scene")
    scene.add_argument("source", type=Path)
    scene.add_argument("output", type=Path)
    scene.add_argument("--thumbnail", type=Path)

    overlay = commands.add_parser("overlay")
    overlay.add_argument("source", type=Path)
    overlay.add_argument("output", type=Path)
    overlay.add_argument("thumbnail", type=Path)
    overlay.add_argument("--target-width", type=int, required=True)
    overlay.add_argument("--left", type=int, required=True)
    overlay.add_argument("--top", type=int, required=True)

    background = commands.add_parser("background")
    background.add_argument("base_source", type=Path)
    background.add_argument("variant_source", type=Path)
    background.add_argument("output", type=Path)
    background.add_argument("thumbnail", type=Path)

    floor = commands.add_parser("floor")
    floor.add_argument("base_source", type=Path)
    floor.add_argument("variant_source", type=Path)
    floor.add_argument("output", type=Path)
    floor.add_argument("thumbnail", type=Path)

    preview = commands.add_parser("preview")
    preview.add_argument("base", type=Path)
    preview.add_argument("output", type=Path)
    preview.add_argument("overlays", nargs="+", type=Path)

    catalog = commands.add_parser("catalog")
    catalog.add_argument("output", type=Path)
    return parser


def main() -> None:
    """명령행 인자에 맞는 에셋 변환 작업을 실행합니다."""

    arguments = _build_parser().parse_args()
    if arguments.command == "scene":
        prepare_scene(
            arguments.source,
            arguments.output,
            arguments.thumbnail,
        )
    elif arguments.command == "overlay":
        prepare_overlay(
            arguments.source,
            arguments.output,
            arguments.thumbnail,
            target_width=arguments.target_width,
            left=arguments.left,
            top=arguments.top,
        )
    elif arguments.command == "background":
        prepare_background_overlay(
            arguments.base_source,
            arguments.variant_source,
            arguments.output,
            arguments.thumbnail,
        )
    elif arguments.command == "floor":
        prepare_floor_overlay(
            arguments.base_source,
            arguments.variant_source,
            arguments.output,
            arguments.thumbnail,
        )
    elif arguments.command == "preview":
        build_preview(
            arguments.base,
            arguments.overlays,
            arguments.output,
        )
    else:
        export_catalog(arguments.output)


if __name__ == "__main__":
    main()
