# AGENTS.md

## 1. Project Role

You are working as a senior frontend engineer and product-minded UI designer for this project.

Your goal is not only to make the code work, but also to make the interface look clean, stable, modern, and production-ready.

This project is a developer-facing / admin-facing system. The UI should prioritize:

* Clarity
* Information density
* Stable layout
* Readability
* Responsive behavior
* Professional visual hierarchy
* No text overflow
* No broken cards
* No uncontrolled horizontal page scroll

The UI should feel closer to:

* Linear
* Vercel
* GitHub
* Notion
* shadcn/ui
* Stripe Dashboard

Avoid overly decorative, childish, colorful, marketing-page-like, or low-density designs.

---

## 2. Frontend Tech Stack Preference

When generating frontend code, prefer the following stack unless the existing project clearly uses something else:

* React
* TypeScript
* Tailwind CSS
* shadcn/ui
* lucide-react icons
* CSS variables for theme tokens
* Component-based structure

When using Tailwind, write clean and maintainable class names. Avoid random excessive styling.

When using shadcn/ui, prefer existing components before creating custom ones.

Common preferred components:

* Button
* Card
* Badge
* Tabs
* Table
* Dialog
* DropdownMenu
* Tooltip
* Sheet
* ScrollArea
* Separator
* Input
* Textarea
* Select
* Progress
* Skeleton
* Alert

---

## 3. Visual Style Rules

The default visual style should be:

* Clean
* Modern
* Calm
* Developer-friendly
* Dashboard-oriented
* Subtle contrast
* Clear spacing
* Clear hierarchy

Use restrained colors.

Preferred UI patterns:

* Soft cards
* Clear section headers
* Compact tables
* Status badges
* Progress indicators
* Empty states
* Loading states
* Error states
* Sticky headers where useful
* Side navigation for complex systems
* Top-level page title + short description
* Action area on the right side of page headers

Avoid:

* Huge gradients unless explicitly requested
* Random bright colors
* Overly large cards
* Unnecessary animations
* Centering everything
* Marketing landing page style
* Giant typography in admin pages
* Uncontrolled shadows
* Layouts that look like demos rather than real products

---

## 4. Critical Layout Safety Rules

These rules are mandatory.

The UI must never break because of long text, long English words, IDs, URLs, SQL, JSON, logs, filenames, email addresses, or model outputs.

### 4.1 Flex and Grid Safety

Every flex or grid child that contains text must be able to shrink.

Use:

```tsx
className="min-w-0"
```

For flexible text containers, prefer:

```tsx
className="flex-1 min-w-0"
```

For grid layouts, use:

```tsx
className="grid-cols-[minmax(0,1fr)]"
```

or ensure grid children have:

```tsx
className="min-w-0"
```

Never allow a text child to define the width of the whole layout.

---

### 4.2 Long Text Rules

For normal paragraphs:

```tsx
className="whitespace-normal break-words"
```

For compact one-line text:

```tsx
className="truncate"
```

For card descriptions:

```tsx
className="line-clamp-2"
```

or:

```tsx
className="line-clamp-3"
```

For URLs, hashes, tokens, long IDs, and unbroken strings:

```tsx
className="break-all"
```

For model output, logs, SQL, JSON, stack traces, or code:

```tsx
className="overflow-x-auto whitespace-pre-wrap break-words"
```

If horizontal scrolling is preferred for code-like content:

```tsx
className="overflow-x-auto whitespace-pre"
```

---

### 4.3 Table Safety

All tables must be wrapped in a horizontal scroll container:

```tsx
<div className="w-full overflow-x-auto">
  <Table>
    ...
  </Table>
</div>
```

For dense tables, prefer:

```tsx
className="table-fixed"
```

For table cells containing long content:

```tsx
className="max-w-[240px] truncate"
```

or:

```tsx
className="max-w-[320px] whitespace-normal break-words"
```

Never let one long cell expand the entire page width.

---

### 4.4 Card Safety

Cards must not break because of child content.

Use:

```tsx
<Card className="min-w-0 overflow-hidden">
```

Inside cards, text containers should use:

```tsx
className="min-w-0"
```

For card titles:

```tsx
className="truncate"
```

For card descriptions:

```tsx
className="line-clamp-2 text-muted-foreground"
```

For generated content or user content inside cards:

```tsx
className="whitespace-normal break-words"
```

---

### 4.5 Page Width Safety

Never hardcode large fixed widths without constraints.

Prefer:

```tsx
className="w-full max-w-7xl mx-auto"
```

or:

```tsx
className="w-full min-w-0"
```

Avoid:

```tsx
className="w-[1200px]"
```

unless there is a clear reason and responsive behavior is handled.

The whole page should not create unwanted horizontal scrolling.

---

## 5. Responsive Design Rules

Every page must work at:

* Mobile width
* Tablet width
* Desktop width
* Wide desktop width

Use responsive Tailwind utilities:

```tsx
className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3"
```

For page layout:

```tsx
className="flex flex-col gap-6"
```

For toolbar/action areas:

```tsx
className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between"
```

For button groups:

```tsx
className="flex flex-wrap items-center gap-2"
```

Do not assume desktop-only layout unless the page is explicitly internal-only and still safe at smaller widths.

---

## 6. Dashboard Page Pattern

For admin/dashboard pages, use this structure:

```tsx
<div className="flex min-w-0 flex-col gap-6">
  <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
    <div className="min-w-0">
      <h1 className="truncate text-2xl font-semibold tracking-tight">
        Page Title
      </h1>
      <p className="mt-1 max-w-2xl text-sm text-muted-foreground">
        Short description of what this page does.
      </p>
    </div>

    <div className="flex flex-wrap items-center gap-2">
      {/* actions */}
    </div>
  </div>

  {/* stats cards */}

  {/* main content */}
</div>
```

Each page should usually include:

* Page title
* Short page description
* Main actions
* Key metrics if applicable
* Main table or content area
* Empty state
* Loading state
* Error state

---

## 7. Form Design Rules

Forms should be clear, compact, and stable.

Use:

* Labels
* Descriptions where needed
* Validation messages
* Proper disabled/loading states
* Clear primary action
* Secondary cancel/back action

Form layout:

```tsx
className="grid gap-4"
```

For two-column forms:

```tsx
className="grid grid-cols-1 gap-4 md:grid-cols-2"
```

Long inputs must not break the layout.

Use:

```tsx
className="min-w-0"
```

on form field wrappers where necessary.

---

## 8. Data / Agent / Report UI Rules

This project may contain data-agent, report-generation, task-queue, SQL, logs, JSON, LLM output, or observability pages.

For these pages, prioritize stability and readability.

### 8.1 SQL Display

SQL must be displayed in a safe code container:

```tsx
<pre className="max-h-[420px] overflow-auto rounded-md border bg-muted p-4 text-sm">
  <code className="whitespace-pre">{sql}</code>
</pre>
```

Do not allow SQL to stretch the page.

---

### 8.2 JSON Display

JSON must be displayed safely:

```tsx
<pre className="max-h-[420px] overflow-auto rounded-md border bg-muted p-4 text-sm">
  <code className="whitespace-pre">
    {JSON.stringify(data, null, 2)}
  </code>
</pre>
```

---

### 8.3 Log Display

Logs should use:

```tsx
className="max-h-[480px] overflow-auto rounded-md border bg-muted p-4 font-mono text-xs"
```

Long log lines should not break the page.

---

### 8.4 LLM Output Display

LLM output may be long and unpredictable.

Use:

```tsx
className="prose prose-sm max-w-none whitespace-normal break-words dark:prose-invert"
```

or a controlled container:

```tsx
className="max-w-none overflow-hidden whitespace-normal break-words text-sm leading-6"
```

Never assume LLM output is short.

---

### 8.5 Task Status UI

For async tasks, use clear status badges.

Suggested statuses:

* PENDING
* RUNNING
* SUCCESS
* FAILED
* CANCELED
* RETRYING

Use consistent visual mapping.

Each task page should show:

* Task ID
* Task type
* Status
* Progress
* Created time
* Started time
* Finished time
* Error message if failed
* Related report ID if applicable

Long task IDs must use:

```tsx
className="font-mono text-xs truncate"
```

or:

```tsx
className="font-mono text-xs break-all"
```

---

## 9. Component Quality Rules

When creating components:

* Use TypeScript types.
* Keep props explicit.
* Avoid deeply nested unreadable JSX.
* Extract repeated UI into components.
* Use semantic HTML where possible.
* Use accessible labels.
* Use loading and empty states.
* Use error boundaries or error display where appropriate.
* Avoid inline magic numbers unless necessary.
* Do not duplicate large UI blocks.

Prefer:

```tsx
type Props = {
  title: string;
  description?: string;
};
```

Avoid using `any` unless there is a strong reason.

---

## 10. State and Data Rules

When implementing data loading:

* Show loading state.
* Show empty state.
* Show error state.
* Avoid blank screens.
* Avoid crashing when fields are missing.
* Be defensive with optional values.

For unknown values, display:

```text
-
```

or:

```text
Unknown
```

Do not render `undefined`, `null`, or `[object Object]` directly.

---

## 11. Empty State Rules

Every important table or list should have an empty state.

Empty states should include:

* A short title
* A helpful description
* Optional action button

Example:

```tsx
<div className="flex min-h-[240px] flex-col items-center justify-center rounded-lg border border-dashed p-8 text-center">
  <h3 className="text-sm font-medium">No reports yet</h3>
  <p className="mt-1 max-w-sm text-sm text-muted-foreground">
    Create a report to start analyzing community sentiment.
  </p>
</div>
```

---

## 12. Loading State Rules

Use skeletons for major content areas.

Avoid layout shift.

For tables, show skeleton rows.

For cards, show skeleton blocks.

For long-running tasks, show progress indicators when progress is available.

---

## 13. Error State Rules

Errors should be visible and useful.

Do not show raw stack traces to normal users.

Developer-facing pages may include expandable technical details.

Use:

* Error title
* Human-readable message
* Retry action if applicable
* Details section for debug info

---

## 14. Accessibility Rules

Basic accessibility is mandatory.

* Buttons must have clear labels.
* Icon-only buttons must have `aria-label`.
* Inputs must have labels.
* Interactive elements must be keyboard accessible.
* Do not use color as the only signal.
* Maintain readable contrast.
* Use semantic elements where possible.

---

## 15. Animation Rules

Use animations sparingly.

Allowed:

* Small hover transitions
* Subtle loading indicators
* Smooth accordion/dialog transitions

Avoid:

* Large page animations
* Bouncy effects
* Decorative animations that distract from data
* Animation-heavy UI for admin systems

---

## 16. Icon Rules

Use icons only when they improve scanning.

Preferred icon library:

```text
lucide-react
```

Icons should be:

```tsx
className="h-4 w-4"
```

or:

```tsx
className="h-5 w-5"
```

Do not overuse icons.

---

## 17. Copywriting Rules

UI text should be clear and concise.

Use professional product language.

Prefer:

```text
Create report
Run analysis
View details
Task failed
No data available
```

Avoid vague text:

```text
Click here
Do thing
Submit stuff
OK
```

For errors, explain what happened and what the user can do next.

---

## 18. Frontend Self-Review Checklist

Before finishing any frontend task, review the generated UI against this checklist:

### Layout

* [ ] No text overflow
* [ ] No broken cards
* [ ] No unwanted full-page horizontal scroll
* [ ] Flex children with text use `min-w-0`
* [ ] Grid children with text use `min-w-0`
* [ ] Long strings use `truncate`, `break-words`, or `break-all`
* [ ] Tables are wrapped in `overflow-x-auto`
* [ ] Code/log/SQL/JSON blocks are scrollable

### Responsive

* [ ] Works on mobile
* [ ] Works on tablet
* [ ] Works on desktop
* [ ] Action buttons wrap safely
* [ ] Cards stack correctly

### UX

* [ ] Loading state exists
* [ ] Empty state exists
* [ ] Error state exists
* [ ] Main action is clear
* [ ] Status is visible and understandable

### Code

* [ ] TypeScript types are clear
* [ ] No unnecessary `any`
* [ ] Components are not overly large
* [ ] Repeated UI is extracted
* [ ] No dead code
* [ ] No console logs unless needed for debugging

---

## 19. Codex / Agent Instruction

When asked to build or modify frontend UI:

1. Read this `AGENTS.md`.
2. Read `DESIGN.md` if it exists.
3. Reuse existing components and design patterns.
4. Use the frontend design skill if available.
5. Prioritize layout stability over decoration.
6. Always prevent text overflow and layout breakage.
7. Implement loading, empty, and error states.
8. After coding, perform the self-review checklist above.
9. If the UI may contain user-generated text, LLM output, logs, SQL, JSON, IDs, URLs, or long English words, explicitly handle overflow.
10. Do not finish until the page is visually stable and production-ready.

---

## 20. Recommended Default Page Container

Use this as the default outer structure for new pages:

```tsx
export function PageShell({
  title,
  description,
  actions,
  children,
}: {
  title: string;
  description?: string;
  actions?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div className="flex min-w-0 flex-col gap-6 p-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <h1 className="truncate text-2xl font-semibold tracking-tight">
            {title}
          </h1>
          {description ? (
            <p className="mt-1 max-w-2xl text-sm text-muted-foreground">
              {description}
            </p>
          ) : null}
        </div>

        {actions ? (
          <div className="flex flex-wrap items-center gap-2">
            {actions}
          </div>
        ) : null}
      </div>

      <div className="min-w-0">
        {children}
      </div>
    </div>
  );
}
```

---

## 21. Recommended Safe Text Utilities

Use these patterns frequently:

### One-line title

```tsx
className="truncate"
```

### Paragraph

```tsx
className="whitespace-normal break-words"
```

### Description in card

```tsx
className="line-clamp-2 text-muted-foreground"
```

### Long ID

```tsx
className="font-mono text-xs break-all"
```

### Table cell with long value

```tsx
className="max-w-[240px] truncate"
```

### Code block

```tsx
className="overflow-x-auto whitespace-pre"
```

### LLM output

```tsx
className="whitespace-normal break-words leading-6"
```

---

## 22. Forbidden Frontend Patterns

Do not generate these patterns unless explicitly required:

```tsx
className="w-[1200px]"
```

without responsive constraints.

```tsx
className="flex"
```

with long text children and no `min-w-0`.

```tsx
<Table>
```

without an `overflow-x-auto` wrapper.

```tsx
<pre>
```

without `overflow-auto` or `overflow-x-auto`.

```tsx
<div>{someObject}</div>
```

when `someObject` may be an object.

```tsx
<p>{possiblyVeryLongText}</p>
```

without `break-words`, `truncate`, or layout constraints.

---

## 23. Final Standard

The final UI should look like a real internal product built by an experienced frontend engineer.

It should not look like a quick AI-generated demo.

The most important rule:

> Never allow content to break the layout.
