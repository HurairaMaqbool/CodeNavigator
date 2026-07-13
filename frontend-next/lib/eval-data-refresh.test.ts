import { describe, expect, it, vi } from "vitest";
import { QueryClient } from "@tanstack/react-query";
import { refreshEvalCachesQuietly } from "@/lib/eval-data-refresh";

describe("refreshEvalCachesQuietly", () => {
  it("invalidates and refetches eval caches without throwing", () => {
    const qc = new QueryClient();
    const invalidate = vi.spyOn(qc, "invalidateQueries");
    const refetch = vi.spyOn(qc, "refetchQueries");
    const setData = vi.spyOn(qc, "setQueryData");

    expect(() =>
      refreshEvalCachesQuietly("repo-9", qc, "unit_test"),
    ).not.toThrow();

    expect(invalidate).toHaveBeenCalledWith({
      queryKey: ["evalHealth", "repo-9"],
    });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["evalHistory"] });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["goldenStatus"] });
    expect(refetch).toHaveBeenCalledWith({
      queryKey: ["evalHealth", "repo-9"],
    });
    expect(refetch).toHaveBeenCalledWith({ queryKey: ["evalHistory"] });
    expect(refetch).toHaveBeenCalledWith({ queryKey: ["goldenStatus"] });
    expect(setData).toHaveBeenCalledWith(
      ["evalAutoLastRefresh", "repo-9"],
      expect.any(Number),
    );
  });
});
