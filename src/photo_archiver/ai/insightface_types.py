"""InsightFace face dict structural contract — typed boundary at the AI adapter.

InsightFace's ``FaceAnalysis.get`` returns a list of face dicts shaped as
``{"bbox": [x1, y1, x2, y2], "det_score": float, "embedding": np.ndarray}`` —
the embedding is a numpy array, all other fields are plain Python types.

The rest of the codebase touches these dicts only through the AI adapter
(`InsightFaceDetector` / `InsightFaceRecognizer`), which copies numpy into
Domain tuples at the boundary so Domain stays numpy-free (ADR-015). This
TypedDict gives the adapter a static contract over the otherwise opaque dict
so ``face["bbox"]`` / ``face["embedding"]`` access is type-checked: future
InsightFace renames (e.g. ``embedding`` → ``normed_embedding``) surface as
mypy errors at the adapter instead of silently breaking the matching pipeline.

MAJOR-3 resolution (Review): replaces ``Any`` on ``extract_from(faces: Any)``
and the detector's ``_to_face_box(face: Any)`` / ``_to_embedding(face: Any)``
helpers with this structural type. ``total=False`` lets callers pass partial
stubs in tests (e.g. a detector stub without ``embedding`` when only boxes are
needed) without losing type precision on the fields that ARE present.

Embedding field honesty: ``embedding`` is typed ``Any`` rather than
``Sequence[float]`` because the adapter calls ``.tolist()`` on it (a numpy
method, not a Sequence method). Pretending Sequence carries ``.tolist()`` would
lie about the type; typing it as ``Any`` is the honest admission that this one
field crosses the numpy boundary at the AI adapter — the adapter's job is
precisely to pull numpy out into Domain tuples here. ``bbox`` and ``det_score``
are plain Python types and stay fully typed.
"""

from typing import Any, TypedDict

from collections.abc import Sequence


class InsightFaceFace(TypedDict, total=False):
    """Structural contract for one face dict returned by ``FaceAnalysis.get``.

    Fields:
        bbox: ``[x1, y1, x2, y2]`` float bounding box in image pixel coords.
            InsightFace emits floats; the detector copies them to ``FaceBox``
            ints at the boundary so Domain stays float-free on box geometry.
        det_score: Detection confidence in ``[0.0, 1.0]`` (InsightFace range).
        embedding: Face embedding vector; numpy.ndarray at runtime. Typed
            ``Any`` here — see module docstring "Embedding field honesty"
            note. The adapter calls ``.tolist()`` (numpy method) at the
            boundary to extract plain floats into ``FaceEmbedding``.
        normed_embedding: Optional normalized embedding; InsightFace emits this
            on some model packs. ``total=False`` makes it optional.
    """

    bbox: Sequence[float]
    det_score: float
    embedding: Any  # numpy.ndarray at runtime — honest Any at the numpy boundary (see module docstring)
    normed_embedding: Any  # numpy.ndarray at runtime — same numpy-boundary honesty as embedding

