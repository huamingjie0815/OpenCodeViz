# Code Graph Legend Filter Design

Date: 2026-04-18
Project: OpenCodeViz
Status: Approved design

## Summary

This change adds interactive type filtering to the `Code` graph legend.

Today the legend is visual only. Users can read the node color mapping, but they cannot reduce graph density from the legend itself. The new behavior turns each code-type legend item into a toggle that hides matching nodes and any connected edges in the `Code` view only.

The filter is multi-select and defaults to showing all types. Search and detail behavior remain based on the full code graph, not only the currently visible subset.

## Goals

- Make the `Code` graph legend clickable.
- Allow users to hide one or more node types independently.
- Remove hidden-type nodes from the rendered graph, not merely dim them.
- Remove edges whose source or target node is hidden.
- Keep the interaction limited to the `Code` view.

## Non-Goals

- Changing `Architecture` view legend or filtering behavior.
- Changing `Flow` view behavior.
- Filtering left sidebar search results by current legend visibility.
- Clearing the right detail panel when the selected node becomes hidden.
- Adding persistence to local storage, URL state, or server-side state.

## Interaction Design

### Legend behavior

In the `Code` view, each supported legend type is rendered as a toggle button:

- `class`
- `function`
- `method`
- `interface`
- `module`

Default state:

- all legend items are active
- all code graph nodes are visible

Click behavior:

- clicking an active legend item hides that type
- clicking an inactive legend item shows that type again
- users may hide multiple types at once
- users may return to the full graph by re-enabling all types

Visual feedback:

- active legend items keep the current filled appearance
- inactive legend items are visibly muted but remain clearly clickable
- the existing label checkbox remains separate and unchanged

### Graph behavior

When one or more legend types are hidden in the `Code` view:

- nodes whose `type` matches a hidden legend type are not rendered
- edges are rendered only when both endpoint nodes remain visible
- the force simulation uses only the visible graph subset
- hover, click, and highlight behavior apply only to visible rendered nodes

### Search and detail behavior

Legend filtering does not change the data source for sidebar features:

- left search continues to search the full `states.code.nodes`
- right detail panel continues to show the last selected node, even if that node is later hidden by the legend
- a hidden selected node is no longer highlighted in the canvas because it is not rendered

This preserves the current mental model that the legend controls canvas visibility only.

## State Design

Add a dedicated `Code`-view legend filter state in the frontend:

- `hiddenCodeTypes`
  - a `Set` of currently hidden node types

This state is frontend-only and resets with page reload.

The source graph remains unchanged:

- `states.code.nodes` stays the full raw node list
- `states.code.links` stays the full raw edge list

Rendering derives a visible subset from the raw state plus `hiddenCodeTypes`.

## Rendering Design

Use render-time filtering instead of CSS-only hiding.

Recommended flow:

1. derive visible code nodes from `states.code.nodes`
2. build a visible node id set
3. derive visible code links from `states.code.links`
4. bind the D3 simulation and DOM only to the visible subset

This avoids stale layout physics from hidden nodes and keeps edge behavior simple.

The filtered subset is used only when:

- `activeView === "code"`

Other views continue using their existing state and rendering paths unchanged.

## Implementation Shape

### Frontend logic

Update `src/codeviz/web/app.js` to:

- track `hiddenCodeTypes`
- render legend items as clickable controls
- ensure node degree calculation for the `Code` view uses the visible links that are actually rendered
- keep search helpers pointed at the unfiltered raw state
- clear canvas highlight safely when the selected node is not part of the visible subset

Add a small pure helper at `src/codeviz/web/code-legend-filter.js` to:

- derive visible code nodes from raw nodes plus `hiddenCodeTypes`
- derive visible code links from raw links plus the visible node id set
- keep the filtering rules deterministic and easy to unit test

`app.js` remains responsible for DOM events, D3 binding, and legend state updates.

### Frontend markup and styles

Update `src/codeviz/web/index.html` to:

- make legend items clickable controls instead of plain static labels
- add active and inactive visual states for legend items
- preserve the current compact in-canvas layout and spacing

No new panel, modal, or toolbar row is needed.

## Testing

Required verification:

- clicking a code legend item toggles that type between visible and hidden
- multiple code legend items can be hidden at the same time
- visible code links exclude edges touching hidden nodes
- the `Code` graph simulation and rendering use only visible nodes
- `Architecture` and `Flow` behaviors remain unchanged
- search helpers still operate on the full code graph data, not the filtered subset

Add focused frontend tests for the pure filtering helper and legend state transitions. DOM click tests are optional; deterministic filtering tests are required.

## Risks And Constraints

- `src/codeviz/web/app.js` already contains shared graph behavior for three views. The legend change must stay scoped to the `Code` path.
- Degree-based node sizing currently depends on rendered graph links. Filtering must not accidentally compute sizes from hidden edges.
- The worktree is already dirty. Implementation changes must remain scoped to the legend interaction and related frontend tests.
