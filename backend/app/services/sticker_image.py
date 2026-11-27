from dataclasses import dataclass
from hashlib import file_digest
from io import BytesIO
from pathlib import Path
from typing import Protocol

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageOps

MODEL = "u2netp"
MODEL_SHA256 = "309c8469258dda742793dce0ebea8e6dd393174f89934733ecc8b14c76f4ddd8"
PROCESSING_VERSION = "paper-edge-v1"


class StickerImageError(ValueError):
    pass


class BackgroundRemovalProvider(Protocol):
    def mask(self, image: Image.Image) -> Image.Image: ...


class OnnxBackgroundRemovalProvider:
    def __init__(self, directory: Path, threads: int):
        weights = directory / f"{MODEL}.onnx"
        with weights.open("rb") as source:
            if file_digest(source, "sha256").hexdigest() != MODEL_SHA256:
                raise StickerImageError("model_unavailable")
        import numpy as np
        import onnxruntime as ort

        options = ort.SessionOptions()
        options.intra_op_num_threads = threads
        options.inter_op_num_threads = 1
        options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        options.enable_cpu_mem_arena = False
        options.enable_mem_pattern = False
        self.session = ort.InferenceSession(str(weights), sess_options=options, providers=["CPUExecutionProvider"])
        self.input = self.session.get_inputs()[0].name
        self.output = self.session.get_outputs()[0].name
        self.np = np

    def mask(self, image):
        # U²-Net 320 px input and RGB normalization follow rembg's u2netp session.
        np = self.np
        rgb = np.asarray(image.resize((320, 320), Image.Resampling.LANCZOS), dtype=np.float32)
        mean = np.array([.485, .456, .406], dtype=np.float32)
        std = np.array([.229, .224, .225], dtype=np.float32)
        normalized = ((rgb / max(float(rgb.max()), 1e-6) - mean) / std).transpose(2, 0, 1)
        mask = self.session.run([self.output], {self.input: normalized[None]})[0][0, 0]
        low, high = float(mask.min()), float(mask.max())
        if not np.isfinite(mask).all() or high - low < 1e-6:
            raise StickerImageError("foreground_uncertain")
        return Image.fromarray(((mask - low) * (255 / (high - low))).clip(0, 255).astype(np.uint8))


class FakeBackgroundRemovalProvider:
    def mask(self, image):
        result = Image.new("L", image.size)
        ImageDraw.Draw(result).ellipse((image.width * .12, image.height * .1, image.width * .88, image.height * .9), fill=255)
        return result


@dataclass
class StickerImages:
    cutout: Image.Image
    sticker: Image.Image

    def thumbnail(self, edge: int) -> Image.Image:
        result = self.sticker.copy()
        result.thumbnail((edge, edge), Image.Resampling.LANCZOS)
        return result


def encode(image):
    with BytesIO() as file:
        image.save(file, "WEBP", lossless=True, method=4)
        return file.getvalue()


def rounded_outline(cutout: Image.Image) -> Image.Image:
    alpha = cutout.getchannel("A")
    radius = max(2, min(12, round(max(cutout.size) * .016)))
    pad = radius + 2
    backing = ImageOps.expand(alpha, border=pad, fill=0)
    expanded = backing.filter(ImageFilter.MaxFilter(radius * 2 + 1))
    expanded = expanded.filter(ImageFilter.GaussianBlur(max(.65, radius / 4)))
    sticker = Image.new("RGBA", expanded.size, (255, 254, 252, 0))
    sticker.putalpha(expanded)
    sticker.alpha_composite(cutout, (pad, pad))
    return sticker


def make_sticker(source: Image.Image, edge: int, provider: BackgroundRemovalProvider | None, crop=None) -> StickerImages:
    image = source.convert("RGBA")
    if crop:
        left, top, width, height = crop
        box = (round(left * image.width), round(top * image.height),
               round((left + width) * image.width), round((top + height) * image.height))
        image = image.crop(box)
        if min(image.size) < 12:
            raise StickerImageError("invalid_crop")
    image.thumbnail((edge, edge), Image.Resampling.LANCZOS)
    if min(image.size) < 12:
        raise StickerImageError("source_invalid")
    if provider:
        matte = Image.new("RGB", image.size, "white")
        original_alpha = image.getchannel("A")
        matte.paste(image, mask=original_alpha)
        if max(high - low for low, high in matte.getextrema()) < 6:
            raise StickerImageError("foreground_uncertain")
        mask = provider.mask(matte).convert("L").resize(image.size, Image.Resampling.LANCZOS)
        mask = mask.point(lambda value: 0 if value < 20 else 255 if value > 236 else value)
        mask = ImageChops.multiply(mask, original_alpha)
        foreground = mask.point(lambda value: 255 if value >= 128 else 0)
        fraction = foreground.histogram()[255] / (image.width * image.height)
        if not .018 <= fraction <= .97:
            raise StickerImageError("foreground_uncertain")
        image.putalpha(mask)
    bounds = image.getchannel("A").getbbox()
    if bounds is None:
        raise StickerImageError("foreground_uncertain")
    cropped = image.crop(bounds)
    return StickerImages(cropped, rounded_outline(cropped))
