"use client";

import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Search, X } from "lucide-react";
import { getSymbols, type SymbolItem } from "@/lib/api";
import { Input } from "@/components/ui/input";

type SymbolSearchBarProps = {
  repoId: string;
  onSelectSymbol: (symbol: SymbolItem) => void;
  disabled?: boolean;
};

export function SymbolSearchBar({
  repoId,
  onSelectSymbol,
  disabled = false,
}: SymbolSearchBarProps) {
  const [symbols, setSymbols] = useState<SymbolItem[]>([]);
  const [query, setQuery] = useState("");
  const [isOpen, setIsOpen] = useState(false);
  const [highlightedIndex, setHighlightedIndex] = useState(-1);
  const [mounted, setMounted] = useState(false);
  const [coords, setCoords] = useState({ top: 0, left: 0, width: 0 });
  const dropdownRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    let active = true;
    async function load() {
      try {
        const data = await getSymbols(repoId);
        if (active) {
          setSymbols(data);
        }
      } catch (e) {
        console.error("Failed to load symbols:", e);
      }
    }
    load();
    return () => {
      active = false;
    };
  }, [repoId]);

  // Close dropdown on click outside
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (
        dropdownRef.current &&
        !dropdownRef.current.contains(event.target as Node) &&
        inputRef.current &&
        !inputRef.current.contains(event.target as Node)
      ) {
        setIsOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, []);

  // Update dropdown coordinates dynamically
  const updateCoords = () => {
    if (inputRef.current) {
      const rect = inputRef.current.getBoundingClientRect();
      setCoords({
        top: rect.bottom,
        left: rect.left,
        width: rect.width,
      });
    }
  };

  useEffect(() => {
    if (isOpen) {
      updateCoords();
      // Listen to scroll events on any parent element (using useCapture = true)
      window.addEventListener("scroll", updateCoords, true);
      window.addEventListener("resize", updateCoords);
    }
    return () => {
      window.removeEventListener("scroll", updateCoords, true);
      window.removeEventListener("resize", updateCoords);
    };
  }, [isOpen]);

  // Fuzzy match query
  const filtered = query.trim()
    ? symbols.filter((sym) => {
        const q = query.toLowerCase();
        const n = sym.name.toLowerCase();
        let qIdx = 0;
        for (let i = 0; i < n.length; i++) {
          if (n[i] === q[qIdx]) {
            qIdx++;
            if (qIdx === q.length) return true;
          }
        }
        return false;
      })
    : symbols;

  const displayList = filtered.slice(0, 15); // Show top 15 results

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (!isOpen) {
      if (e.key === "ArrowDown" || e.key === "Enter") {
        setIsOpen(true);
      }
      return;
    }

    if (e.key === "ArrowDown") {
      e.preventDefault();
      setHighlightedIndex((prev) =>
        prev < displayList.length - 1 ? prev + 1 : 0
      );
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setHighlightedIndex((prev) =>
        prev > 0 ? prev - 1 : displayList.length - 1
      );
    } else if (e.key === "Enter") {
      e.preventDefault();
      if (highlightedIndex >= 0 && highlightedIndex < displayList.length) {
        const selected = displayList[highlightedIndex];
        if (selected) {
          onSelectSymbol(selected);
          setQuery(selected.name);
          setIsOpen(false);
        }
      } else if (displayList.length > 0) {
        const first = displayList[0];
        if (first) {
          onSelectSymbol(first);
          setQuery(first.name);
          setIsOpen(false);
        }
      }
    } else if (e.key === "Escape") {
      setIsOpen(false);
    }
  };

  return (
    <div className="relative w-full">
      <div className="relative flex items-center">
        <Search className="absolute left-3 h-4 w-4 text-muted-foreground pointer-events-none" />
        <Input
          ref={inputRef}
          type="text"
          className="pl-9 pr-9 w-full bg-surface border-border text-sm rounded-lg focus-visible:ring-1 focus-visible:ring-primary"
          placeholder="Go to Symbol (fuzzy match e.g. Session.send)..."
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setIsOpen(true);
            setHighlightedIndex(-1);
            // Re-calculate coordinate positions when input width/height might shift slightly
            setTimeout(updateCoords, 0);
          }}
          onFocus={() => {
            setIsOpen(true);
            updateCoords();
          }}
          onKeyDown={handleKeyDown}
          disabled={disabled}
        />
        {query && (
          <button
            type="button"
            className="absolute right-3 p-0.5 rounded-full hover:bg-surface-hover text-muted-foreground transition-colors"
            onClick={() => {
              setQuery("");
              setIsOpen(false);
              inputRef.current?.focus();
            }}
          >
            <X className="h-3.5 w-3.5" />
          </button>
        )}
      </div>

      {/* Render overlay dropdown menu using React Portal to prevent container clipping */}
      {mounted && isOpen && displayList.length > 0 &&
        createPortal(
          <div
            ref={dropdownRef}
            className="fixed rounded-lg border border-border bg-surface-raised shadow-xl overflow-hidden"
            style={{
              top: `${coords.top + 6}px`,
              left: `${coords.left}px`,
              width: `${coords.width}px`,
              zIndex: 9999,
            }}
          >
            <ul className="max-h-60 overflow-y-auto py-1 text-sm text-foreground">
              {displayList.map((item, index) => {
                const isHighlighted = index === highlightedIndex;
                return (
                  <li key={item.id}>
                    <button
                      type="button"
                      className={`flex w-full flex-col px-4 py-2 text-left hover:bg-surface-hover transition-colors ${
                        isHighlighted ? "bg-surface-hover" : ""
                      }`}
                      onClick={() => {
                        onSelectSymbol(item);
                        setQuery(item.name);
                        setIsOpen(false);
                      }}
                    >
                      <span className="font-semibold text-foreground">
                        {item.name}
                      </span>
                      <span className="text-xs text-muted-foreground truncate">
                        {item.path} · {item.type}
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
          </div>,
          document.body
        )}

      {mounted && isOpen && query.trim() && displayList.length === 0 &&
        createPortal(
          <div
            ref={dropdownRef}
            className="fixed rounded-lg border border-border bg-surface-raised px-4 py-3 shadow-xl text-sm text-muted-foreground"
            style={{
              top: `${coords.top + 6}px`,
              left: `${coords.left}px`,
              width: `${coords.width}px`,
              zIndex: 9999,
            }}
          >
            No matching symbols found.
          </div>,
          document.body
        )}
    </div>
  );
}
