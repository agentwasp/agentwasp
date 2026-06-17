"""Memory Hub — all memory layers in one place."""

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy import desc, func, select

from ...db.models import (
    BehavioralRule,
    DreamLog,
    KnowledgeNode,
    KnowledgeRelation,
    MemoryEntry,
    ProceduralMemory,
    WorldTimeline,
)
from ...db.session import async_session
from ...memory.types import MemoryQuery, MemoryType

router = APIRouter()

VALID_TABS = {"store", "kg", "procedural", "timeline", "dreams"}


@router.get("/", response_class=HTMLResponse)
async def memory_list(
    request: Request,
    tab: str = Query(default="store"),
    type: str = Query(default=""),
    search: str = Query(default=""),
    page: int = Query(default=1, ge=1),
):
    if tab not in VALID_TABS:
        tab = "store"

    memory = request.app.state.memory
    per_page = 20
    offset = (page - 1) * per_page

    # ── Counts (all from DB for coherence with search results) ────────────
    layer_counts = {}
    stats: dict = {}
    async with async_session() as session:
        for Model, key in [
            (ProceduralMemory, "procedural"),
            (BehavioralRule,   "behavioral"),
            (DreamLog,         "dreams"),
            (WorldTimeline,    "timeline"),
            (KnowledgeNode,    "kg_nodes"),
            (KnowledgeRelation,"kg_relations"),
        ]:
            r = await session.execute(select(func.count(Model.id)))
            layer_counts[key] = r.scalar() or 0

        # Store tab stats from DB so they match what retrieve() actually returns
        type_rows = await session.execute(
            select(MemoryEntry.memory_type, func.count(MemoryEntry.id))
            .group_by(MemoryEntry.memory_type)
        )
        stats = {mt.value: 0 for mt in MemoryType}
        for mem_type, count in type_rows.fetchall():
            stats[mem_type] = count
        stats["total"] = sum(stats.values())
        stats["size_bytes"] = memory.store.total_size_bytes()

    # ── Tab-specific data ──────────────────────────────────────────────────
    entries      = []
    procedural   = []
    timeline     = []
    dreams       = []
    kg_nodes      = []
    kg_relations  = []
    kg_node_names = {}

    if tab == "store":
        query = MemoryQuery(limit=per_page, offset=offset)
        if type and type in [mt.value for mt in MemoryType]:
            query.memory_type = MemoryType(type)
        if search:
            query.text_search = search
        async with async_session() as session:
            entries = await memory.retrieve(session, query)

    elif tab == "procedural":
        async with async_session() as session:
            r = await session.execute(
                select(ProceduralMemory)
                .order_by(desc(ProceduralMemory.created_at))
                .limit(per_page).offset(offset)
            )
            procedural = list(r.scalars().all())

    elif tab == "timeline":
        async with async_session() as session:
            r = await session.execute(
                select(WorldTimeline).order_by(desc(WorldTimeline.observed_at))
                .limit(per_page).offset(offset)
            )
            timeline = list(r.scalars().all())

    elif tab == "dreams":
        async with async_session() as session:
            r = await session.execute(
                select(DreamLog).order_by(desc(DreamLog.started_at))
                .limit(per_page).offset(offset)
            )
            dreams = list(r.scalars().all())

    elif tab == "kg":
        async with async_session() as session:
            rn = await session.execute(
                select(KnowledgeNode)
                .order_by(desc(KnowledgeNode.created_at))
                .limit(per_page).offset(offset)
            )
            kg_nodes = list(rn.scalars().all())
            rr = await session.execute(
                select(KnowledgeRelation)
                .order_by(desc(KnowledgeRelation.created_at))
                .limit(per_page).offset(offset)
            )
            kg_relations = list(rr.scalars().all())
            # Build name lookup from ALL nodes referenced by this page's relations
            # so relation endpoints show names even when those nodes are on other pages
            referenced_ids = {r.from_node_id for r in kg_relations} | {r.to_node_id for r in kg_relations}
            known_ids = {n.id for n in kg_nodes}
            missing_ids = referenced_ids - known_ids
            extra_nodes = []
            if missing_ids:
                rextra = await session.execute(
                    select(KnowledgeNode.id, KnowledgeNode.name)
                    .where(KnowledgeNode.id.in_(missing_ids))
                )
                extra_nodes = rextra.all()
            kg_node_names = {n.id: n.name for n in kg_nodes}
            kg_node_names.update({row.id: row.name for row in extra_nodes})

    if getattr(memory, "backend", "internal") == "supermemory":
        stats = memory.get_stats()

    return request.app.state.templates.TemplateResponse(request, "memory.html", {
        "stats":         stats,
        "memory_backend": getattr(memory, "backend", "internal"),
        "supermemory_status": memory.supermemory_status() if hasattr(memory, "supermemory_status") else {},
        "migration_preview": memory.migration_preview() if hasattr(memory, "migration_preview") else {},
        "current_type":  type,
        "search":        search,
        "page":          page,
        "per_page":      per_page,
        "tab":           tab,
        "layer_counts":  layer_counts,
        "entries":       entries,
        "procedural":    procedural,
        "timeline":      timeline,
        "dreams":        dreams,
        "kg_nodes":      kg_nodes,
        "kg_relations":  kg_relations,
        "kg_node_names": kg_node_names,
    })


@router.get("/api/supermemory/migration-preview")
async def supermemory_migration_preview(request: Request, limit: int = Query(default=500, ge=1, le=5000)):
    memory = request.app.state.memory
    if not hasattr(memory, "migration_preview"):
        return JSONResponse({"ok": False, "error": "memory manager does not support migration preview"}, status_code=404)
    return JSONResponse({"ok": True, "preview": memory.migration_preview(limit=limit)})


@router.post("/api/supermemory/migrate")
async def supermemory_migrate(request: Request):
    memory = request.app.state.memory
    body = await request.json()
    direction = body.get("direction", "internal_to_supermemory")
    dry_run = bool(body.get("dry_run", True))
    limit = int(body.get("limit", 500) or 500)
    chat_id = str(body.get("chat_id", "") or "")
    project_id = body.get("project_id") or None
    async with async_session() as session:
        if direction == "internal_to_supermemory" and hasattr(memory, "export_internal_to_supermemory"):
            result = await memory.export_internal_to_supermemory(session, limit=limit, dry_run=dry_run, chat_id=chat_id, project_id=project_id)
        elif direction == "supermemory_to_internal" and hasattr(memory, "import_supermemory_to_internal"):
            result = await memory.import_supermemory_to_internal(session, limit=limit, dry_run=dry_run, chat_id=chat_id, project_id=project_id)
        else:
            return JSONResponse({"ok": False, "error": "unknown migration direction"}, status_code=400)
    status_code = 200 if result.get("ok", False) or dry_run else 500
    return JSONResponse({"ok": bool(result.get("ok", False)), "result": result}, status_code=status_code)


@router.get("/{memory_type}/{memory_id}", response_class=HTMLResponse)
async def memory_detail(request: Request, memory_type: str, memory_id: str):
    memory = request.app.state.memory
    entry = None
    try:
        async with async_session() as session:
            entry = await memory.get(session, MemoryType(memory_type), memory_id)
    except ValueError:
        pass

    return request.app.state.templates.TemplateResponse(request, "memory_detail.html", {
        "entry": entry,
    })
