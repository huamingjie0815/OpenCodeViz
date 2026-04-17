# Architecture Interaction Adjustment Design

Date: 2026-04-17
Project: OpenCodeViz
Status: Approved design

## Summary

This change adjusts interaction only in the `Architecture` view.

The current architecture cards drill down immediately on click. That makes it hard to inspect local dependencies before leaving the current level. The new behavior keeps click-to-drill-down, but adds hover-based relationship highlighting so users can inspect dependency context before navigating.

The drill-down stack remains `module -> file -> entity`. A lightweight back action is required after drill-down. The back action only returns to the previous level. It does not preserve a full visit history.

## Goals

- Keep the existing three-level architecture drill-down.
- Add hover highlighting for the hovered card, directly related cards, and connecting lines.
- Keep click behavior for drill-down to avoid adding a new interaction model.
- Add a clear back action in drilled-down architecture pages.
- Limit changes to the `Architecture` view.

## Non-Goals

- Changing `Code Graph` interactions.
- Changing `Flow` interactions.
- Adding right-click menus.
- Adding URL, browser history, or deep-link state for architecture navigation.
- Adding multi-step navigation history.

## Interaction Design

### Hover behavior

In the `Architecture` view, hovering a card should:

- highlight the hovered card
- highlight cards directly connected by an incoming or outgoing edge
- highlight the relevant connecting edges
- dim unrelated cards and edges

When the pointer leaves the card:

- if no other architecture card is hovered, restore the default graph state

This applies at all three architecture levels:

- module level
- file level
- entity level

### Click behavior

Click behavior remains the drill-down trigger:

- module card click opens file level for that module
- file card click opens entity level for that file
- entity card click shows details only and does not drill further

### Back behavior

Back navigation is limited to one level up:

- file level shows a back action to return to module level
- entity level shows a back action to return to the parent file level

No full browsing history is stored. The only required context is the current parent module id and current parent file path.

## State Design

The frontend keeps a small architecture navigation context:

- `architectureViewMode`
  - existing level marker: `module`, `file`, or `entity`
- `architectureContext.moduleId`
  - set when entering file level
- `architectureContext.filePath`
  - set when entering entity level

This is enough to support:

- rendering the current level
- rendering the correct back target
- restoring the previous level without depending on browser history

No state changes are required for the code graph or flow views.

## UI Changes

Add one small back button inside the graph area:

- hidden at architecture module level
- visible at architecture file level and entity level
- positioned with the existing in-canvas controls

No new page, modal, or sidebar section is introduced.

## Implementation Plan

### Frontend logic

Update `src/codeviz/web/app.js` to:

- add architecture-specific hover highlight handlers
- keep current architecture click-to-drill-down behavior
- track minimal parent context for back navigation
- add a single `goBackArchitectureLevel()` action
- ensure clearing and re-rendering resets highlight state correctly between levels

### Frontend markup and styles

Update `src/codeviz/web/index.html` to:

- add a back button in the graph canvas control area
- add minimal styles for the back control
- add architecture highlight styles only where needed

## Testing

Required verification:

- module hover highlights directly connected modules and edges
- file hover highlights directly connected files and edges
- clicking a module still enters file level
- clicking a file still enters entity level
- back from file level returns to module level
- back from entity level returns to file level

If DOM-level hover automation is awkward in the current test harness, the implementation should still add at least one focused frontend test for back-navigation state and document any remaining manual verification.

## Risks And Constraints

- Architecture module level uses custom SVG node and edge rendering, while file and entity levels reuse force-graph rendering. Hover highlighting must work in both rendering paths.
- The current codebase has shared highlight helpers for non-architecture views. The architecture interaction change should avoid regressions in `Code Graph` and `Flow`.
- The worktree is already dirty, so changes must remain scoped to the architecture interaction files and related tests only.
