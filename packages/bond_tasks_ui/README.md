# bond_tasks_ui

Task widgets for the bond apps (Flutter; `bond_tasks`, `bond_ui`).

`BondTaskList`, `BondTaskRow`, `BondTaskForm`, `BondTaskQuickAdd`, `BondChecklist`, `BondTaskChecklistEditor`,
`BondTaskSummaryCard`, `BondTaskDeleteControl`. Strings come from `TaskLabels`. Nothing opens over the page:
delete confirms in place and the date, time and select pickers expand in the flow.

Pass the person's wall date as `today`; the widgets never read the device clock for grouping. Composite widgets take a
`semanticsPrefix` (for example `sdk.tasks`) and derive the ids of their parts.
