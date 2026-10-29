import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { CommandBlock } from "./CommandBlock";
import { EvidenceChips } from "./EvidenceChips";
import { OriginBadge, SeverityBadge, StrengthBadge } from "./ui/Badge";
import { renderApp } from "../test/render";

describe("OriginBadge", () => {
  it.each([
    ["observed", /^observed$/i],
    ["runbook", /^runbook$/i],
    ["rule", /^rule$/i],
    ["ai_hypothesis", /^ai hypothesis$/i],
  ])("says in words where %s content comes from", (origin, text) => {
    render(<OriginBadge origin={origin} />);
    expect(screen.getByText(text)).toBeInTheDocument();
  });
});

describe("StrengthBadge and SeverityBadge", () => {
  it("never shows a percentage for strength", () => {
    render(<StrengthBadge strength="moderate" reason="because" />);
    expect(screen.getByText(/moderate/i)).toBeInTheDocument();
    expect(screen.queryByText(/%/)).toBeNull();
  });
  it("shows the severity as a word", () => {
    render(<SeverityBadge severity="critical" />);
    expect(screen.getByText(/critical/i)).toBeInTheDocument();
  });
});

describe("CommandBlock", () => {
  it("shows commands as text with a notice and no run button", () => {
    render(<CommandBlock commands={["systemctl restart api", "rm -rf /tmp/x"]} />);
    expect(screen.getByText(/systemctl restart api/)).toBeInTheDocument();
    expect(screen.getByText(/does not run commands/i)).toBeInTheDocument();
    expect(screen.queryByRole("button")).toBeNull();
  });
  it("renders nothing when there are no commands", () => {
    const { container } = render(<CommandBlock commands={[]} />);
    expect(container).toBeEmptyDOMElement();
  });
});

describe("EvidenceChips", () => {
  it("shows the first few ids and expands the rest", async () => {
    renderApp(<EvidenceChips ids={[1, 2, 3, 4, 5, 6, 7]} max={3} />);
    expect(screen.getAllByRole("button", { name: /open log record/i })).toHaveLength(3);
    await userEvent.click(screen.getByRole("button", { name: "+4 more" }));
    expect(screen.getAllByRole("button", { name: /open log record/i })).toHaveLength(7);
  });
  it("renders nothing for an empty list", () => {
    const { container } = renderApp(<EvidenceChips ids={[]} />);
    expect(container).toBeEmptyDOMElement();
  });
});
