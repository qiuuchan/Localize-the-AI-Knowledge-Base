import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { DashboardPage } from "../pages/DashboardPage";
import { getJSON } from "../lib/api";

vi.mock("../lib/api", () => ({
  getJSON: vi.fn(),
  postJSON: vi.fn(),
}));

const baseOverview = {
  health: { online: true, endpoints: {} },
  degradations_24h: [],
  kb_stats: {
    database_count: 0,
    document_count: 0,
    chunk_count: 0,
    databases: [],
  },
  drift: { qdrant_points: 0, keyword_chunks: 0, drift: 0, ok: true },
  system: { version: "1.3.0", data_dir_size_mb: 0, uptime_seconds: 0 },
  timestamp: new Date().toISOString(),
};

describe("DashboardPage cost-alert 卡片", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("level=0 时只显示进度条,无告警 banner", async () => {
    vi.mocked(getJSON).mockImplementation(async (path) => {
      if (path === "/dashboard/overview") {
        return {
          ...baseOverview,
          cost_alert: {
            level: 0,
            today_yuan: 100,
            month_yuan: 250,
            month: "2026-07",
            thresholds: { warn: 500, high: 1000, block: 1500 },
            updated_at: "2026-07-21T16:00:00Z",
          },
        };
      }
      throw new Error("eval endpoint unavailable in test");
    });

    render(<DashboardPage />);
    await waitFor(() => {
      expect(screen.getByTestId("cost-bar-fill")).toBeInTheDocument();
    });
    expect(screen.queryByTestId("cost-alert-banner")).not.toBeInTheDocument();
  });

  it("level>=2 时显示橙色告警 banner", async () => {
    vi.mocked(getJSON).mockImplementation(async (path) => {
      if (path === "/dashboard/overview") {
        return {
          ...baseOverview,
          cost_alert: {
            level: 2,
            today_yuan: 600,
            month_yuan: 1100,
            month: "2026-07",
            thresholds: { warn: 500, high: 1000, block: 1500 },
            updated_at: "2026-07-21T16:00:00Z",
          },
        };
      }
      throw new Error("eval endpoint unavailable in test");
    });

    render(<DashboardPage />);
    await waitFor(() => {
      expect(screen.getByTestId("cost-alert-banner")).toBeInTheDocument();
    });
    expect(screen.getByTestId("cost-alert-banner").textContent).toMatch(
      /接近 block 阈值/,
    );
  });

  it("cost_alert 为空(后端 default sentinel)时显示\"用量数据采集中...\"", async () => {
    vi.mocked(getJSON).mockImplementation(async (path) => {
      if (path === "/dashboard/overview") {
        return {
          ...baseOverview,
          // 模拟后端 _COST_ALERT_DEFAULT 哨兵:空字符串 month + updated_at
          cost_alert: {
            level: 0,
            today_yuan: 0,
            month_yuan: 0,
            month: "",
            updated_at: "",
            thresholds: { warn: 500, high: 1000, block: 1500 },
          },
        };
      }
      throw new Error("eval endpoint unavailable in test");
    });

    render(<DashboardPage />);
    await waitFor(() => {
      expect(screen.getByText("用量数据采集中...")).toBeInTheDocument();
    });
    expect(screen.queryByTestId("cost-alert-banner")).not.toBeInTheDocument();
  });
});
