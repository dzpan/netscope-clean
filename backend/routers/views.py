"""Saved Views and Annotations router endpoints."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from fastapi import APIRouter, HTTPException

from backend.models import (
    Annotation,
    AnnotationRequest,
    SavedView,
    SavedViewRequest,
)
from backend.store import view_store

router = APIRouter()


@router.get("/views", tags=["Saved Views"])
async def list_views(session_id: str | None = None) -> list[SavedView]:
    """List saved topology views, optionally filtered by session."""
    return view_store.list_all(session_id=session_id)


@router.get("/views/{view_id}", tags=["Saved Views"])
async def get_view(view_id: str) -> SavedView:
    """Get a single saved view by ID."""
    view = view_store.get(view_id)
    if view is None:
        raise HTTPException(status_code=404, detail="Saved view not found")
    return view


@router.post("/views", status_code=201, tags=["Saved Views"])
async def create_view(body: SavedViewRequest) -> SavedView:
    """Create a new saved topology view."""
    now = datetime.now(UTC)
    view = SavedView(
        view_id=uuid4().hex,
        session_id=body.session_id,
        name=body.name,
        description=body.description,
        is_default=body.is_default,
        zoom=body.zoom,
        pan_x=body.pan_x,
        pan_y=body.pan_y,
        node_positions=body.node_positions,
        protocol_filter=body.protocol_filter,
        vlan_filter=body.vlan_filter,
        annotations=body.annotations,
        created_at=now,
        updated_at=now,
    )
    await view_store.save(view)
    return view


@router.put("/views/{view_id}", tags=["Saved Views"])
async def update_view(view_id: str, body: SavedViewRequest) -> SavedView:
    """Update an existing saved view."""
    existing = view_store.get(view_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Saved view not found")
    now = datetime.now(UTC)
    updated = existing.model_copy(
        update={
            "name": body.name,
            "description": body.description,
            "is_default": body.is_default,
            "session_id": body.session_id,
            "zoom": body.zoom,
            "pan_x": body.pan_x,
            "pan_y": body.pan_y,
            "node_positions": body.node_positions,
            "protocol_filter": body.protocol_filter,
            "vlan_filter": body.vlan_filter,
            "annotations": body.annotations,
            "updated_at": now,
        }
    )
    await view_store.save(updated)
    return updated


@router.delete("/views/{view_id}", tags=["Saved Views"])
async def delete_view(view_id: str) -> dict[str, str]:
    """Delete a saved view."""
    deleted = await view_store.delete(view_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Saved view not found")
    return {"status": "deleted"}


@router.patch("/views/{view_id}/rename", tags=["Saved Views"])
async def rename_view(view_id: str, body: dict[str, str]) -> SavedView:
    """Rename a saved view."""
    name = body.get("name", "").strip()
    if not name:
        raise HTTPException(status_code=422, detail="Name is required")
    view = await view_store.rename(view_id, name)
    if view is None:
        raise HTTPException(status_code=404, detail="Saved view not found")
    return view


@router.patch("/views/{view_id}/default", tags=["Saved Views"])
async def set_default_view(view_id: str) -> SavedView:
    """Set a view as the default for its session."""
    view = view_store.get(view_id)
    if view is None:
        raise HTTPException(status_code=404, detail="Saved view not found")
    now = datetime.now(UTC)
    updated = view.model_copy(update={"is_default": True, "updated_at": now})
    await view_store.save(updated)
    return updated


@router.post("/views/{view_id}/annotations", status_code=201, tags=["Saved Views"])
async def add_annotation(view_id: str, body: AnnotationRequest) -> SavedView:
    """Add an annotation to a saved view."""
    view = view_store.get(view_id)
    if view is None:
        raise HTTPException(status_code=404, detail="Saved view not found")
    now = datetime.now(UTC)
    ann = Annotation(
        annotation_id=uuid4().hex,
        target_type=body.target_type,
        target_id=body.target_id,
        text=body.text,
        color=body.color,
        x=body.x,
        y=body.y,
        created_at=now,
        updated_at=now,
    )
    updated = view.model_copy(
        update={
            "annotations": [*view.annotations, ann],
            "updated_at": now,
        }
    )
    await view_store.save(updated)
    return updated


@router.put("/views/{view_id}/annotations/{annotation_id}", tags=["Saved Views"])
async def update_annotation(view_id: str, annotation_id: str, body: AnnotationRequest) -> SavedView:
    """Update an annotation on a saved view."""
    view = view_store.get(view_id)
    if view is None:
        raise HTTPException(status_code=404, detail="Saved view not found")
    now = datetime.now(UTC)
    found = False
    new_annotations: list[Annotation] = []
    for ann in view.annotations:
        if ann.annotation_id == annotation_id:
            found = True
            new_annotations.append(
                ann.model_copy(
                    update={
                        "target_type": body.target_type,
                        "target_id": body.target_id,
                        "text": body.text,
                        "color": body.color,
                        "x": body.x,
                        "y": body.y,
                        "updated_at": now,
                    }
                )
            )
        else:
            new_annotations.append(ann)
    if not found:
        raise HTTPException(status_code=404, detail="Annotation not found")
    updated = view.model_copy(update={"annotations": new_annotations, "updated_at": now})
    await view_store.save(updated)
    return updated


@router.delete("/views/{view_id}/annotations/{annotation_id}", tags=["Saved Views"])
async def delete_annotation(view_id: str, annotation_id: str) -> SavedView:
    """Delete an annotation from a saved view."""
    view = view_store.get(view_id)
    if view is None:
        raise HTTPException(status_code=404, detail="Saved view not found")
    new_annotations = [a for a in view.annotations if a.annotation_id != annotation_id]
    if len(new_annotations) == len(view.annotations):
        raise HTTPException(status_code=404, detail="Annotation not found")
    now = datetime.now(UTC)
    updated = view.model_copy(update={"annotations": new_annotations, "updated_at": now})
    await view_store.save(updated)
    return updated
