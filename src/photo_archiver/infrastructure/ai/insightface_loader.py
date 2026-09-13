"""InsightFace model pack loader.

Loads and configures :class:`insightface.app.FaceAnalysis` from a model
directory on disk. This adapter isolates filesystem access and the
InsightFace construction API from the ``ai/`` layer so ``ai/`` modules stay
focused on detection/recognition behaviour against a pre-built analysis
instance.
"""

import sys
from pathlib import Path

from insightface.app import FaceAnalysis  # type: ignore[import-untyped]
from loguru import logger

_DEFAULT_MODEL_NAME = "buffalo_l"
_DEFAULT_DET_SIZE = (640, 640)
_DEFAULT_DET_THRESHOLD = 0.5


class ModelPackMissing(Exception):
    """Raised when the requested InsightFace model pack is absent on disk."""


class InsightFaceLoader:
    """Build and prepare ``FaceAnalysis`` instances from a model directory.

    The loader checks the model pack exists before construction so callers
    receive :class:`ModelPackMissing` early rather than crashing inside
    InsightFace internals. The prepared analysis instance is returned to the
    ``ai/`` layer, which only performs detection/recognition against it.
    """

    def __init__(
        self,
        model_root: Path,
        name: str = _DEFAULT_MODEL_NAME,
        det_size: tuple[int, int] = _DEFAULT_DET_SIZE,
        det_threshold: float = _DEFAULT_DET_THRESHOLD,
    ) -> None:
        """Store the model root and detection configuration.

        Args:
            model_root: Directory containing the named model pack subdirectory.
            name: Model pack name recognised by InsightFace.
            det_size: Detection input size in pixels.
            det_threshold: Minimum detection confidence retained, in ``[0.0, 1.0]``.
        """
        self._model_root = model_root
        self._name = name
        self._det_size = det_size
        self._det_threshold = det_threshold

    @property
    def pack_path(self) -> Path:
        """Return the expected model pack subdirectory path."""
        return self._model_root / self._name

    def is_available(self) -> bool:
        """Return whether the named model pack contains loadable onnx files.

        只查目录非空不够——双嵌套等错误布局也会让目录存在（真实用户安装
        曾暴露，2026-09-13）。必须存在 *.onnx 才算可用。
        """
        return self.pack_path.exists() and any(self.pack_path.glob("*.onnx"))

    def load(self) -> FaceAnalysis:
        """Build and prepare a ``FaceAnalysis`` instance from the model pack.

        Raises:
            ModelPackMissing: When the model pack directory is absent or
                contains no loadable onnx files.
        """
        if not self.is_available():
            hint = (
                "run 'PhotoArchiver-cli.exe download-models' in the install directory"
                if getattr(sys, "frozen", False)
                else "run scripts/download_models.py to fetch it"
            )
            raise ModelPackMissing(
                f"InsightFace model pack (onnx files) not found at {self.pack_path}; {hint}"
            )
        # FaceAnalysis's `root` is the parent directory of the named pack;
        # it internally joins `root/name` to locate model files.
        # Phase 7 (ADR-033, W2-1/W2-2 owner 拍板 2026-08-29): load only the
        # modules production consumes — detection + recognition. The pack's
        # landmark models (1k3d68 + 2d106det, 35.4 ms/photo) and genderage
        # (9.8 ms/photo) are dead weight: zero consumers in src (grep-verified;
        # the Person entity has no gender/age fields). Removal measured
        # 254.4 → 128.2 ms/photo (1.985×) with byte-identical bbox/kps/
        # embedding outputs (tools/spike_segment_profile.py v2 A/B experiment).
        # LIMIT-006 后续（离线包缺陷，2026-09-13）：insightface 内部会给 root
        # **自行追加一层 `models`**（ensure_available: root/models/name）——传
        # model_root 本身会导致它去 `model_root/models/<pack>` 找模型而找不到，
        # 继而触发 insightface 自建下载（直连 GitHub、无 sha256 校验，离线包
        # 内置的模型被无视）。正确语义：root = model_root 的父目录。
        analysis = FaceAnalysis(
            name=self._name,
            root=str(self._model_root.parent),
            allowed_modules=("detection", "recognition"),
        )
        analysis.prepare(
            ctx_id=0,
            det_thresh=self._det_threshold,
            det_size=self._det_size,
        )
        logger.debug(
            "InsightFaceLoader prepared pack {} from {} (det_size={}, det_thresh={})",
            self._name,
            self.pack_path,
            self._det_size,
            self._det_threshold,
        )
        return analysis
