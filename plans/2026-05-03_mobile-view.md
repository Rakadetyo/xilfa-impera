# Mobile View Implementation Plan

**Goal:** Make all `/manage` pages usable on mobile. Tables become card lists on mobile, grids get responsive breakpoints, padding shrinks, overflowing rows wrap.

**Stack:** Tailwind CSS (CDN), Jinja2 templates. No build step — all changes are Tailwind utility classes.

**Breakpoint reference:**
- `md:` = 768px+ (tablet/desktop) — use as the desktop threshold
- `sm:` = 640px+ — use for intermediate 2-column layouts

---

## Lessons Learned (from implementation)

### 1. Don't mask overflow — fix the source
`overflow-x: hidden` on `<body>` does NOT prevent viewport-level horizontal scroll (body propagation only works when body has `overflow: visible`). Adding it to `<html>` stops scrolling but clips real content instead. **Always find and fix the actual overflowing element.**

### 2. Bangers `text-3xl` in a flex row overflows on mobile
Long titles using the Bangers display font at `text-3xl` (e.g. "SAT, 02 MAY 2026 @ JETZ STADIUM") exceed 400–430px viewport width. When a title sits in a `flex` row with a sibling button, the row overflows and the button goes off-screen.

**Pattern:**
```html
<div class="flex items-center gap-2">
  <h1 class="text-xl md:text-3xl font-display tracking-wide flex-1 min-w-0">{{ title }}</h1>
  <form class="flex-shrink-0">...</form>
</div>
```
- `flex-1 min-w-0` on the title allows it to shrink and wrap
- `flex-shrink-0` on the sibling keeps it visible
- `text-xl md:text-3xl` reduces font size on mobile to help fit single-line

### 3. Stat cards with currency values need reduced padding on mobile
`p-6` + `grid-cols-3` gives ~100px inner width per card — too narrow for "Rp400,000". Currency values also need smaller font on mobile.

**Pattern:**
```html
<div class="grid grid-cols-2 md:grid-cols-3 gap-4">
  <div class="bg-white rounded-xl border border-gray-200 p-4 md:p-6">
    <div class="text-xl md:text-2xl font-bold">Rp{{ value }}</div>
    <div class="text-gray-500 text-sm">Label</div>
  </div>
</div>
```

### 4. Check detail pages when fixing list pages
The plan listed `partners/list.html` but not `partners/detail.html`. When a list page links to a detail page, the detail page also needs mobile fixes (table → cards, padding, stat grids). Always check the full flow.

### 5. Implementation order: simplest first
Start with pages that have no table→card conversion needed (arena, partners/list). Use them to establish and verify the pattern, then apply to complex pages (players, members, games/detail).

---

**Core pattern for table → cards:**
```html
<!-- Table: hidden on mobile, shown on md+ -->
<div class="hidden md:block">
  <table>...</table>
</div>

<!-- Cards: shown on mobile, hidden on md+ -->
<div class="md:hidden space-y-3">
  {% for item in items %}
  <div class="bg-white border border-gray-200 rounded-lg p-4">
    ...card content...
  </div>
  {% endfor %}
</div>
```

---

## Phase 1 — High Priority (Most used on mobile)

### 1. `app/templates/dashboard.html` ✅ DONE

**Problem areas and exact fixes:**

**Header bar** (line 38–47):
- `px-8 py-4` → `px-4 md:px-8 py-4`
- `flex justify-between items-center` → `flex flex-wrap justify-between items-center gap-2`
- The right-side div with username + role badge + links: add `hidden md:flex` to hide the "Hi, username" + role badge span on mobile (keep Home + Logout links)
  - Wrap username span in `<span class="hidden md:inline">Hi, <strong>...</strong> <span>role</span></span>`

**Stats cards** (line 51–72):
- `grid grid-cols-5 gap-4 mb-8` → `grid grid-cols-2 md:grid-cols-5 gap-4 mb-8`

**Quick Actions** (line 77):
- `<div class="flex gap-4">` → `<div class="flex flex-wrap gap-3">`
- Each button `px-4 py-2` → also add `text-sm` for mobile compactness

**Game sessions grid** (line 106):
- `grid grid-cols-2 gap-4 mb-8` → `grid grid-cols-1 md:grid-cols-2 gap-4 mb-8`

**Navigation grid** (line 168):
- `grid grid-cols-3 gap-4` → `grid grid-cols-2 md:grid-cols-3 gap-4`

**Content padding** (line 49):
- `<div class="p-8">` → `<div class="p-4 md:p-8">`

---

### 1b. `app/templates/games/new.html` ✅ DONE, `games/edit.html` ✅ DONE

**Fixes applied:**
- `p-8` → `p-4 md:p-8`
- Price grid `grid-cols-2` → `grid-cols-1 sm:grid-cols-2`
- Duration/session/max grid `grid-cols-3` → `grid-cols-1 md:grid-cols-3`
- Submit row `flex gap-4` → `flex flex-wrap gap-4`

---

### 2. `app/templates/games/list.html`

**Problem areas and exact fixes:**

**Header** (line 39–60):
- `px-8 py-3` → `px-4 md:px-8 py-3`
- The inner `flex justify-between items-center` div: wrap children on mobile
  - `<div class="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3">`
- View toggle + New Game button container: `<div class="flex items-center gap-4">` → `<div class="flex items-center gap-2 flex-wrap">`

**Card carousel container** (line 63):
- `class="flex-1 flex flex-col items-center justify-center pt-2 pb-2 overflow-hidden"` — no change needed, cards are already w-80 which fits on mobile
- However, the `h-[85vh]` container may be too tall on mobile — change to `h-[70vh] md:h-[85vh]`

**Calendar view** — this is already hidden by default. The calendar grid cells `h-28` will be tight on very small screens. Inside `renderDayCell` in the JS, the cell height is set via CSS class string in JS. This is complex JS-rendered content; wrap the calendar container in `overflow-x-auto` as a quick fix:
- Line 165: `<div id="calendar-view" class="hidden w-full max-w-4xl mx-auto">` → `<div id="calendar-view" class="hidden w-full max-w-4xl mx-auto overflow-x-auto px-2">`

**"+ New Game" button padding** (line 55):
- `px-6 py-3` → `px-4 py-2 md:px-6 md:py-3 text-sm md:text-base`

---

### 3. `app/templates/games/detail.html` ← Most important page

**Main layout padding** (line 67):
- `<main class="ml-0 md:ml-64 pt-14 md:pt-0 flex-1 p-8">` → `<main class="ml-0 md:ml-64 pt-14 md:pt-0 flex-1 p-4 md:p-8">`

**Page header** (lines 68–96) — the title area with back link and delete button. No change needed, already small.

**Tab bar** (lines 99–109):
- `<nav class="flex gap-6">` → `<nav class="flex gap-4 overflow-x-auto pb-1 scrollbar-none">`
- This lets the tab bar scroll horizontally on mobile without wrapping

#### Tab: Overview

**Analytics row** (line 116):
- `grid grid-cols-3 gap-4` → `grid grid-cols-1 sm:grid-cols-3 gap-4`

**Setup Progress steps** (line 275):
- `grid grid-cols-4 gap-4` → `grid grid-cols-2 md:grid-cols-4 gap-4`

**Summary grid** (line 301):
- `grid grid-cols-2 gap-4` → `grid grid-cols-1 md:grid-cols-2 gap-4`

#### Tab: General

**Event Details form grid** (line 483):
- `grid grid-cols-3 gap-6` → `grid grid-cols-1 md:grid-cols-3 gap-4 md:gap-6`

**Pricing & Capacity grid** (line 510):
- `grid grid-cols-3 gap-6` → `grid grid-cols-1 md:grid-cols-3 gap-4 md:gap-6`

**Session Settings grid** (line 529):
- `grid grid-cols-2 gap-6` → `grid grid-cols-1 md:grid-cols-2 gap-4 md:gap-6`

**Services grid** (line 544):
- `grid grid-cols-3 gap-6` → `grid grid-cols-2 md:grid-cols-3 gap-4`

**Partners & Services section** (line 573):
- Partners grid (line 575): `grid grid-cols-3 gap-6` → `grid grid-cols-2 md:grid-cols-3 gap-4`
- Add Partner form row (line 593): `flex flex-wrap gap-2 mb-3` — already wraps, good. But inputs may still overflow. Add `w-full md:w-auto` to the partner name input.

#### Tab: Players

**This is the most critical mobile fix. The attendee table has 7 columns and will not work on mobile.**

**Add Existing Players form** (line 692):
- `<div class="flex gap-4">` → `<div class="flex flex-col sm:flex-row gap-3">`
- Select and button each get `w-full sm:w-auto`

**Desktop table** (lines 779–862): Wrap in `hidden md:block`:
```html
<div class="hidden md:block bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
  <table class="w-full">
    ... (existing table, unchanged) ...
  </table>
</div>
```

**Mobile cards** (insert after the desktop table div): Add this block:
```html
<!-- Mobile attendee cards -->
<div class="md:hidden space-y-3">
  {% set max_players = game.max_players or 25 %}
  {% for i in range(max_players) %}
  {% set a = attendees[i] if i < attendees|length else none %}
  {% if a %}
  <div class="bg-white rounded-xl border border-gray-200 p-4">
    <div class="flex justify-between items-start mb-2">
      <div>
        <p class="font-medium">{{ a.name }}</p>
        <p class="text-sm text-gray-500">{{ a.nickname or '-' }}</p>
      </div>
      <div class="flex items-center gap-1">
        <button type="button"
          onclick="openEditModal('{{ a.id }}', '{{ a.name }}', '{{ a.nickname or '' }}', '{{ a.position_1 or '' }}', '{{ a.position_2 or '' }}', '{{ a.skill_level or 3 }}')"
          class="p-1.5 text-gray-500 hover:text-accent hover:bg-gray-100 rounded">
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z"/></svg>
        </button>
        <form method="post" action="/manage/games/{{ game.id }}/attendees/{{ a.id }}/delete" onsubmit="return confirm('Remove player?')">
          <button type="submit" class="p-1.5 text-red-500 hover:text-red-700 hover:bg-red-50 rounded">
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/></svg>
          </button>
        </form>
      </div>
    </div>
    <div class="flex flex-wrap gap-2 text-xs">
      <span class="px-2 py-1 bg-gray-100 rounded">{{ a.position_1 or '-' }}</span>
      <span class="px-2 py-1 bg-yellow-100 text-yellow-700 rounded">{{ skill_labels.get(a.skill_level, 'Intermediate') }}</span>
      {% if a.team_name_assigned %}
      <span class="px-2 py-1 rounded text-white" style="background-color: {{ a.team_color or '#6B7280' }}">{{ a.team_name_assigned }}</span>
      {% endif %}
    </div>
    <div class="flex gap-2 mt-3">
      <form method="post" action="/manage/games/{{ game.id }}/attendees/{{ a.id }}/pay" class="flex-1">
        <button type="submit" class="w-full px-2 py-1.5 rounded text-sm font-medium
          {% if a.is_paid %}bg-green-100 text-green-700{% else %}bg-gray-100 text-gray-500{% endif %}">
          {{ 'Paid' if a.is_paid else 'Unpaid' }}
        </button>
      </form>
      <form method="post" action="/manage/games/{{ game.id }}/attendees/{{ a.id }}/attend" class="flex-1">
        <button type="submit" class="w-full px-2 py-1.5 rounded text-sm font-medium
          {% if a.is_attend %}bg-green-100 text-green-700{% else %}bg-gray-100 text-gray-500{% endif %}">
          {{ 'Attend: Yes' if a.is_attend else 'Attend: No' }}
        </button>
      </form>
    </div>
  </div>
  {% else %}
  <!-- Empty slots: skip on mobile, they add noise -->
  {% endif %}
  {% endfor %}
  {% if not attendees %}
  <p class="text-center text-gray-400 py-8">No players yet.</p>
  {% endif %}
</div>
```

**Note:** The empty slot rows (when `a` is None) are deliberately skipped in the mobile card view. They only serve as visual capacity indicators on desktop. The player count line already shows `X / Y Players` above the list.

#### Tab: Teams

**Player value list** — the `grid-cols-3` grid for player value badges (around lines 940–970):
- Find: `<div class="grid grid-cols-3 gap-2 max-h-64 overflow-y-auto pr-1">` (or similar)
- Change to: `<div class="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-2 max-h-64 overflow-y-auto pr-1">`

**Team config form** (line 983):
- `<div class="flex flex-wrap gap-4 mb-5">` — already wraps, no change needed

**Balance Score section** (around line 1097):
- Any `flex` rows with many items: add `flex-wrap`

**Generated teams display** — after line 1094, there will be team column cards. Find the teams grid and change:
- `grid grid-cols-N` for N teams → wrap with `overflow-x-auto` or use `grid-cols-1 sm:grid-cols-2 md:grid-cols-3`

#### Tab: Schedule

Read the schedule tab content (lines 1100+) and apply similar responsive grid fixes. The schedule table (if any) should get `overflow-x-auto` wrapper. Match card format for mobile.

---

## Phase 2 — Data Management Pages

### 4. `app/templates/players.html`

**Header bar** (lines 39–47):
- `px-8 py-4` → `px-4 md:px-8 py-4`
- Wrap the right-side items: hide username/role on mobile same as dashboard

**Content padding** (line 50):
- `<div class="p-8">` → `<div class="p-4 md:p-8">`

**Stats cards** (line 64):
- `grid grid-cols-3 gap-4 mb-8` → `grid grid-cols-1 sm:grid-cols-3 gap-4 mb-6`

**Add New Player form** (line 102):
- `grid grid-cols-4 gap-4` → `grid grid-cols-2 md:grid-cols-4 gap-3 md:gap-4`
- The `col-span-4` submit row → `col-span-2 md:col-span-4`

**Search & Filter form** (line 169):
- Already has `flex flex-wrap gap-4` — good. But `flex-1 min-w-[200px]` search box may still cause overflow on very small screens.
- Change search box: `flex-1 min-w-[200px]` → `flex-1 min-w-[150px]`
- Filter + Clear buttons: keep as-is, they'll wrap naturally

**Desktop table** (lines 224–325): Wrap entire table div in `hidden md:block`:
```html
<div class="hidden md:block bg-white border border-gray-200 rounded-lg overflow-hidden shadow-sm">
  <table class="w-full">
    ... (unchanged) ...
  </table>
  ... (pagination, unchanged) ...
</div>
```

**Mobile player cards** (insert after desktop table div):
```html
<!-- Mobile player cards -->
<div class="md:hidden space-y-3">
  {% for p in players %}
  <div class="bg-white border border-gray-200 rounded-lg p-4 cursor-pointer"
    onclick="openPlayerModal({{ p.id }}, '{{ p.name }}', '{{ p.nickname or '' }}', '{{ p.position_1 or '' }}', '{{ p.position_2 or '' }}', {{ p.skill_level }}, '{{ p.contact_no or '' }}', '{{ p.instagram or '' }}', '{{ p.reclub or '' }}', '{{ p.join_date or '' }}', {{ p.status if p.status is not none else 1 }})">
    <div class="flex justify-between items-start mb-2">
      <div>
        <p class="font-bold">{{ p.name }}</p>
        <p class="text-sm text-gray-500">{{ p.nickname or '-' }}</p>
      </div>
      <div class="flex flex-wrap gap-1 justify-end">
        {% set status_map = {1: 'Active', 0: 'Inactive', -1: 'Blacklisted'} %}
        {% set status_colors = {1: 'bg-green-100 text-green-700', 0: 'bg-gray-100 text-gray-600', -1: 'bg-red-100 text-red-700'} %}
        <span class="px-2 py-0.5 text-xs font-bold rounded {{ status_colors.get(p.status, 'bg-gray-100 text-gray-600') }}">
          {{ status_map.get(p.status, 'Active') }}
        </span>
      </div>
    </div>
    <div class="flex flex-wrap gap-1 text-xs">
      {% if p.position_1 or p.position_2 %}
      <span class="px-2 py-1 bg-gray-100 rounded font-bold">{{ p.position_1 or '' }}{% if p.position_1 and p.position_2 %}/{{ p.position_2 }}{% endif %}</span>
      {% endif %}
      {% set skill_map = {1: 'Newbie', 2: 'Beginner', 3: 'Intermediate', 4: 'Expert', 5: 'Pro'} %}
      <span class="px-2 py-1 rounded font-bold {% if p.skill_level >= 4 %}bg-green-100 text-green-700{% elif p.skill_level >= 3 %}bg-yellow-100 text-yellow-700{% else %}bg-gray-100 text-gray-600{% endif %}">
        {{ skill_map[p.skill_level] }}
      </span>
      <span class="px-2 py-1 bg-gray-50 text-gray-500 rounded">Joined: {{ p.join_date[:10] if p.join_date else '-' }}</span>
      <span class="px-2 py-1 bg-gray-50 text-gray-500 rounded">Last: {{ p.last_played[:10] if p.last_played else '-' }}</span>
    </div>
  </div>
  {% endfor %}
  {% if not players %}
  <p class="text-center text-gray-400 py-8">No players found.</p>
  {% endif %}
</div>
```

**Mobile pagination** — pagination is inside the desktop table div, so it'll be hidden on mobile. Add a second copy of the pagination block below the mobile cards, wrapped in `md:hidden`. Copy the exact same pagination HTML from inside the desktop table.

---

### 5. `app/templates/members.html`

**Header bar** (lines 38–47):
- `px-8 py-4` → `px-4 md:px-8 py-4`
- Hide username/role on mobile (same as other pages)

**Content padding** (line 49):
- `<div class="p-8">` → `<div class="p-4 md:p-8">`

**Stats cards** (line 51):
- `grid grid-cols-3 gap-4 mb-8` → `grid grid-cols-1 sm:grid-cols-3 gap-4 mb-6`

**Action buttons row** (lines 140–148):
- `<div class="flex gap-2">` containing 3 buttons → `<div class="flex flex-wrap gap-2">`

**Desktop table** (lines 152–196): Wrap in `hidden md:block`:
```html
<div class="hidden md:block bg-white border border-gray-200 rounded-lg overflow-hidden shadow-sm">
  <table class="w-full">
    ... (unchanged) ...
  </table>
</div>
```

**Mobile member cards** (insert after desktop table div):
```html
<!-- Mobile member cards -->
<div class="md:hidden space-y-3">
  {% for m in members %}
  {% if m %}
  <div class="bg-white border border-gray-200 rounded-lg p-4 cursor-pointer"
    onclick="openMemberModal({{ m.id }}, {{ m.player_id }}, '{{ m.member_start_date or '' }}', '{{ m.member_end_date or '' }}', {{ m.is_paid }}, {{ m.membership_price or 0 }})">
    <div class="flex justify-between items-start mb-2">
      <div>
        <p class="font-bold">{{ m.name }}{% if m.nickname %} <span class="text-gray-400 font-normal">({{ m.nickname }})</span>{% endif %}</p>
        <p class="text-sm text-gray-500">{{ m.member_period or '-' }}</p>
      </div>
      <span onclick="event.stopPropagation(); togglePaid({{ m.id }}, {{ m.is_paid }})"
        class="cursor-pointer px-2 py-1 text-xs font-bold rounded hover:opacity-80 {% if m.is_paid %}bg-green-100 text-green-700{% else %}bg-red-100 text-red-700{% endif %}">
        {{ 'Paid' if m.is_paid else 'Unpaid' }}
      </span>
    </div>
    <div class="flex flex-wrap gap-x-4 gap-y-1 text-xs text-gray-500">
      <span>Start: {{ m.member_start_date or '-' }}</span>
      <span>End: {{ m.member_end_date or 'Ongoing' }}</span>
      <span>Price: {{ (m.membership_price or 0)|int }}</span>
      <span>Members: {{ m.n_members or 0 }}</span>
    </div>
  </div>
  {% endif %}
  {% endfor %}
  {% if not members %}
  <p class="text-center text-gray-400 py-8">No members this month.</p>
  {% endif %}
</div>
```

---

## Phase 3 — Setup / Config Pages

### 6. `app/templates/arena.html`

**Header bar** (lines 41–50):
- `px-8 py-4` → `px-4 md:px-8 py-4`
- Hide username/role on mobile

**Content padding** (line 52):
- `<div class="p-8">` → `<div class="p-4 md:p-8">`

**Stats cards** (line 54):
- `grid grid-cols-3 gap-4 mb-8` → `grid grid-cols-2 md:grid-cols-3 gap-4 mb-6`

**Arena cards grid** (line 85):
- Already has `grid-cols-1 md:grid-cols-2 lg:grid-cols-3` — no change needed

**Note:** arena.html uses cards (not table) for arenas — already mostly mobile friendly. Main fixes are just padding and stats row.

---

### 7. `app/templates/users.html` ✅ DONE

**Header bar** (lines 38–47):
- `px-8 py-4` → `px-4 md:px-8 py-4`
- Hide username/role on mobile

**Content padding** (line 49):
- `<div class="p-8">` → `<div class="p-4 md:p-8">`

**Create User form** (line 66):
- `<form action="/manage/users" method="POST" class="flex gap-4">` → `<form action="/manage/users" method="POST" class="flex flex-col sm:flex-row gap-3">`
- Add `w-full sm:w-auto` to the submit button

**Desktop table** (lines 93–154): Wrap in `hidden md:block`:
```html
<div class="hidden md:block bg-white border border-gray-200 rounded-lg overflow-hidden shadow-sm">
  <table class="w-full">
    ... (unchanged) ...
  </table>
</div>
```

**Mobile user cards**:
```html
<!-- Mobile user cards -->
<div class="md:hidden space-y-3">
  {% for u in users %}
  <div class="bg-white border border-gray-200 rounded-lg p-4">
    <div class="flex justify-between items-start mb-2">
      <div>
        <p class="font-bold">{{ u.username }}</p>
        <p class="text-xs text-gray-400">ID: {{ u.id }} · Created: {{ u.created_at[:10] }}</p>
      </div>
      <div class="flex flex-col gap-1 items-end">
        <span class="px-2 py-0.5 text-xs font-bold rounded {% if u.role == 'superadmin' %}bg-purple-100 text-purple-700{% else %}bg-gray-100 text-gray-600{% endif %}">{{ u.role }}</span>
        {% if u.invite_token %}
        <span class="px-2 py-0.5 text-xs font-bold rounded bg-yellow-100 text-yellow-700">Invite Pending</span>
        {% else %}
        <span class="px-2 py-0.5 text-xs font-bold rounded bg-green-100 text-green-700">Active</span>
        {% endif %}
      </div>
    </div>
    {% if u.id != user.id %}
    <div class="flex gap-2 flex-wrap mt-2">
      {% if u.invite_token %}
      <button onclick="showInviteModal('{{ u.username }}', '{{ u.invite_token }}')"
        class="px-3 py-1 text-xs font-bold text-accent border border-accent rounded hover:bg-accent hover:text-black transition-colors">Show Invite Link</button>
      {% else %}
      <form method="POST" action="/manage/users/{{ u.id }}/invite" style="display:inline;">
        <button type="submit" class="px-3 py-1 text-xs font-bold text-blue-600 border border-blue-300 rounded hover:bg-blue-50 transition-colors">Resend Invite</button>
      </form>
      {% endif %}
      {% if user.role == 'superadmin' %}
      <button onclick="deleteUser({{ u.id }}, '{{ u.username }}')"
        class="px-3 py-1 text-xs font-bold text-red-600 hover:text-red-700">Delete</button>
      {% endif %}
    </div>
    {% else %}
    <p class="text-xs text-gray-400 mt-2">(you)</p>
    {% endif %}
  </div>
  {% endfor %}
  {% if not users %}
  <p class="text-center text-gray-400 py-8">No users yet.</p>
  {% endif %}
</div>
```

---

### 8. `app/templates/partners/list.html`

**Header** (line 37):
- `<div class="flex justify-between items-center mb-8">` — no change needed, it's just a title + button

**Filter tabs** (line 46):
- `<div class="flex gap-2 mb-6 border-b border-gray-200 pb-3">` → `<div class="flex gap-2 mb-6 border-b border-gray-200 pb-3 overflow-x-auto">`

**Partners grid** (line 59):
- `grid grid-cols-3 gap-5` → `grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-4 md:gap-5`

**Content padding** (line 36):
- `<main class="ml-0 md:ml-64 pt-14 md:pt-0 flex-1 p-8">` → `<main class="ml-0 md:ml-64 pt-14 md:pt-0 flex-1 p-4 md:p-8">`

---

### 9. `app/templates/partners/detail.html` ✅ DONE, `partners/edit.html` ✅ DONE, `partners/new.html` ✅ DONE

**partners/detail.html** (done):
- `p-8` → `p-4 md:p-8` on main
- Header: `flex-wrap gap-3`, button `px-4 py-2 md:px-6 md:py-3 flex-shrink-0`
- Stats: `grid-cols-3 gap-6` → `grid-cols-2 md:grid-cols-4 gap-4`, `p-6` → `p-4 md:p-6`, added Rating as 4th card, removed stars from header
- Game History table → `hidden md:block` + mobile card list (`md:hidden divide-y`)

**partners/edit.html**, **partners/new.html** (pending):
- `p-8` padding → `p-4 md:p-8`
- `grid-cols-2` or `grid-cols-3` forms → `grid-cols-1 md:grid-cols-2` / `grid-cols-1 md:grid-cols-3`
- Any wide `flex` rows with many items → `flex-wrap`

---

## Header pattern (applies to all pages with top bar)

Every manage page has this header pattern:
```html
<header class="bg-white border-b border-gray-200 px-8 py-4 flex justify-between items-center">
    <h1 class="text-lg font-display">Page Title</h1>
    <div class="flex items-center gap-4">
        <span class="text-xs text-gray-600">Hi, <strong>{{ user.username }}</strong> <span class="text-xs bg-accent/20 text-accent px-2 py-0.5 rounded">{{ user.role }}</span></span>
        <a href="/manage" class="text-sm text-accent hover:underline">Dashboard</a>
        <form method="POST" action="/manage/logout">
            <button type="submit" class="text-sm text-red-600 hover:text-red-700">Logout</button>
        </form>
    </div>
</header>
```

Change to:
```html
<header class="bg-white border-b border-gray-200 px-4 md:px-8 py-4 flex justify-between items-center">
    <h1 class="text-lg font-display">Page Title</h1>
    <div class="flex items-center gap-3">
        <span class="hidden md:inline text-xs text-gray-600">Hi, <strong>{{ user.username }}</strong> <span class="text-xs bg-accent/20 text-accent px-2 py-0.5 rounded">{{ user.role }}</span></span>
        <a href="/manage" class="text-sm text-accent hover:underline">Dashboard</a>
        <form method="POST" action="/manage/logout">
            <button type="submit" class="text-sm text-red-600 hover:text-red-700">Logout</button>
        </form>
    </div>
</header>
```

This pattern repeats across: `players.html`, `members.html`, `arena.html`, `users.html`. Apply it to all of them.

---

## What NOT to change

- `_sidebar.html` — already mobile-ready with hamburger, overlay, slide-in
- All modals (memberModal, playerModal, etc.) — already use `max-w-sm/md w-full mx-4` which is mobile-safe
- The `games/list.html` card carousel — already works on mobile (single card centered)
- `invite/` templates — already have mobile-first design from a recent redesign

---

## Testing checklist (after implementing)

For each page, verify at 375px wide (iPhone SE viewport):

- [ ] `dashboard.html` — stats show 2 columns, buttons wrap, no horizontal scroll
- [ ] `games/list.html` — header wraps, card carousel shows, + New Game button visible
- [ ] `games/detail.html` — all tabs accessible, players tab shows cards, forms stack vertically
- [ ] `players.html` — cards show with correct data, pagination works, filter form wraps
- [ ] `members.html` — cards show with paid toggle working, action buttons visible
- [ ] `arena.html` — stats show 2 columns, arena cards single column
- [ ] `users.html` — create form stacks, cards show with invite/delete actions
- [ ] `partners/list.html` — filter tabs scrollable, partners show 1 column
