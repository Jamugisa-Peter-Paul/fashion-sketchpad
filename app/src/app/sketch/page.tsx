"use client";

import { Eraser, Eye, EyeOff, PenLine, Redo2, Trash2, Undo2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import { guidePath } from "@/components/BodyThumb";
import { SketchCanvas } from "@/components/sketch/SketchCanvas";
import { BottomBar, Button, Spinner, TopBar, cx } from "@/components/ui";
import { labelOf, useCatalog } from "@/lib/catalog";
import { useDraft, useDraftHydrated, type Stroke, type Tool } from "@/lib/draft";
import { ERASER_SIZES, PEN_SIZES, hasInk } from "@/lib/strokes";
import { VIEW_LABELS, type ViewName } from "@/lib/types";
import { useAuthedImage } from "@/lib/useAuthedImage";

const EMPTY: Stroke[] = [];
const CLEAR: Stroke = { tool: "clear", size: 0, points: [], pressure: false };

function ToolButton({
  label,
  active,
  onClick,
  disabled,
  small,
  children,
}: {
  label: string;
  active?: boolean;
  onClick: () => void;
  disabled?: boolean;
  small?: boolean;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      aria-pressed={active}
      disabled={disabled}
      onClick={onClick}
      className={cx(
        "grid shrink-0 place-items-center rounded-xl transition-colors",
        small ? "size-9 md:size-12" : "size-10 md:size-12",
        active ? "bg-ink text-white" : "text-ink active:bg-line/70",
        disabled && "opacity-30",
      )}
    >
      {children}
    </button>
  );
}

export default function SketchPage() {
  const router = useRouter();
  const hydrated = useDraftHydrated();
  const catalog = useCatalog((s) => s.catalog);
  const draft = useDraft();
  const [view, setView] = useState<ViewName>("front");
  const [tool, setTool] = useState<Tool>("pen");
  const [penSize, setPenSize] = useState<number>(PEN_SIZES[1]);
  const [eraserSize, setEraserSize] = useState<number>(ERASER_SIZES[1]);
  const [showGuide, setShowGuide] = useState(true);
  const [redoStack, setRedoStack] = useState<Partial<Record<ViewName, Stroke[]>>>({});
  const { url: guideUrl } = useAuthedImage(draft.body ? guidePath(draft.body, view) : null, { offline: true });
  const missingChoices = hydrated && (!draft.body || !draft.garment);

  useEffect(() => {
    if (missingChoices) router.replace("/new/");
  }, [missingChoices, router]);

  if (!hydrated || missingChoices) return <Spinner />;

  const body = catalog?.bodies.find((b) => b.id === draft.body);
  const views: ViewName[] = body?.views.length ? body.views : ["front", "back"];
  const drawn = draft.drawn[view];
  const strokes = drawn?.strokes ?? EMPTY;
  const redo = redoStack[view] ?? EMPTY;
  const sizes = tool === "pen" ? PEN_SIZES : ERASER_SIZES;
  const size = tool === "pen" ? penSize : eraserSize;
  const anyInk = views.some((v) => hasInk(draft.drawn[v]));

  function change(next: Stroke[]) {
    draft.setStrokes(view, next);
    setRedoStack((r) => ({ ...r, [view]: [] }));
  }
  function undo() {
    const last = strokes.at(-1);
    if (!last) return;
    draft.setStrokes(view, strokes.slice(0, -1));
    setRedoStack((r) => ({ ...r, [view]: [...redo, last] }));
  }
  function redoLast() {
    const next = redo.at(-1);
    if (!next) return;
    draft.setStrokes(view, [...strokes, next]);
    setRedoStack((r) => ({ ...r, [view]: redo.slice(0, -1) }));
  }

  const tools = (
    <>
      <ToolButton label="Pen" active={tool === "pen"} onClick={() => setTool("pen")}>
        <PenLine className="size-5" />
      </ToolButton>
      <ToolButton label="Eraser" active={tool === "eraser"} onClick={() => setTool("eraser")}>
        <Eraser className="size-5" />
      </ToolButton>
      <span className="h-8 w-px shrink-0 bg-line md:my-1 md:h-px md:w-8" />
      {sizes.map((s) => (
        <ToolButton key={s} small label={`Size ${s}`} active={size === s} onClick={() => (tool === "pen" ? setPenSize(s) : setEraserSize(s))}>
          <span className="rounded-full bg-current" style={{ width: Math.min(4 + s * (tool === "pen" ? 1.4 : 0.35), 22), height: Math.min(4 + s * (tool === "pen" ? 1.4 : 0.35), 22) }} />
        </ToolButton>
      ))}
      <span className="h-8 w-px shrink-0 bg-line md:my-1 md:h-px md:w-8" />
      <ToolButton label="Undo" onClick={undo} disabled={!strokes.length}>
        <Undo2 className="size-5" />
      </ToolButton>
      <ToolButton label="Redo" onClick={redoLast} disabled={!redo.length}>
        <Redo2 className="size-5" />
      </ToolButton>
      <ToolButton label="Clear" onClick={() => change([...strokes, CLEAR])} disabled={!hasInk(drawn)}>
        <Trash2 className="size-5" />
      </ToolButton>
    </>
  );

  return (
    <div className="flex h-dvh flex-col">
      <TopBar
        title={`Draw your ${labelOf(catalog?.garments, draft.garment).toLowerCase()}`}
        back="/new/"
        step={1}
      />

      <div className="mx-auto flex w-full max-w-6xl gap-2 px-4 pt-3" role="tablist">
        {views.map((v) => (
          <button
            key={v}
            type="button"
            role="tab"
            aria-selected={view === v}
            onClick={() => setView(v)}
            className={cx(
              "flex min-h-10 items-center gap-2 rounded-full px-4 text-sm font-medium",
              view === v ? "bg-ink text-white" : "bg-surface text-ink",
            )}
          >
            {VIEW_LABELS[v]}
            {hasInk(draft.drawn[v]) && <span className={cx("size-1.5 rounded-full", view === v ? "bg-white" : "bg-accent")} />}
          </button>
        ))}
        <button
          type="button"
          onClick={() => setShowGuide(!showGuide)}
          className="ml-auto flex min-h-10 items-center gap-1.5 rounded-full px-3 text-sm text-muted active:bg-line/60"
        >
          {showGuide ? <Eye className="size-4" /> : <EyeOff className="size-4" />}
          Outline
        </button>
      </div>

      <div className="mx-auto flex min-h-0 w-full max-w-6xl flex-1 flex-col gap-2 px-2 py-2 md:flex-row md:px-4">
        <div className="hidden flex-col items-center gap-1 rounded-2xl bg-surface p-1 md:flex">{tools}</div>
        <div className="min-h-0 flex-1">
          <SketchCanvas
            strokes={strokes}
            base={drawn?.base}
            guideUrl={guideUrl}
            showGuide={showGuide}
            tool={tool}
            size={size}
            onChange={change}
          />
        </div>
        <div className="flex items-center justify-between gap-0.5 overflow-x-auto rounded-2xl bg-surface p-1 md:hidden">{tools}</div>
      </div>

      <BottomBar>
        <Button block disabled={!anyInk} onClick={() => router.push("/style/")}>
          {anyInk ? "Next: style" : "Draw your garment over the outline"}
        </Button>
      </BottomBar>
    </div>
  );
}
