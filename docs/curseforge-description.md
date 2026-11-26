# CurseForge page: Azeroth GPS

What goes on the CurseForge project page (project 1712208), with the project's settings. Paste everything under
Description into the Description, in CurseForge's Markdown editor. The pictures are azerothgps.com's `/press/` copies
(the website's PRESS.md); the links go to the site. 1.4.0's text needs `/press/stormwind-citygrid-3d.webp` and
the guide's `/guide/routing/` page live first: paste it once the release has deployed the site.

## Project settings

- **Links:** Issues: https://azerothgps.com/feedback/ · Wiki: https://azerothgps.com/guide/ · Source: none (the repo is
  going private) · Discord: https://discord.gg/hHEguxVQFb

---

## Description

**Basically a car GPS, but for Azeroth.** Tell it where you want to go and it draws the way there, with turn-by-turn directions, distances and an ETA.

_Every feature, option and command is in the **[AzerothGPS guide](https://azerothgps.com/guide/)**._

![From the Crossroads to Ashenvale: the stop picked, then the route up the Gold Road with a detour to learn a flight path](https://azerothgps.com/press/routes-zones-125.gif)

---

# New in 1.4.0: routing just got a whole lot better

![Stormwind's Trade District with the city grid's walkable cells and a route over them](https://azerothgps.com/press/stormwind-citygrid-3d.webp)

*   **Walks the real ground.** Routes follow the map's own terrain, streets, stairs, bridges and floors, built from the game's own collision, so they go where you can actually walk.
*   **Walls are walls.** No more routes through rock, fences or palisades. Caves, dungeons and buildings are entered through their doors.
*   **Floors and stairs.** Stacked cities and buildings are handled floor by floor, and it tells you when your stop is above or below you.
*   **Spell jumping.** Have Slow Fall, Levitate or a racial like Walk on Air? Routes can jump off cliffs instead of walking the long way, and tell you when to cast, with a button to click.
*   **Safe drop.** Choose how far you'll fall without a spell. Jumps show as coils on the map; right-click one to avoid it.
*   **Your call on roads.** One slider from "Stick to roads" to "Cut across".
*   **Enemy areas.** The other faction's guards near you or your route show in red; routes go round them, or ask first.
*   **Fast.** Routes are worked out in the background without stalling your game.

_How it works, and why other routes walk you into walls: **[the routing page](https://azerothgps.com/guide/routing/)**._

---

# What it does

*   **Every way to get around:** roads and terrain, flight paths (with a detour to learn new ones), boats and zeppelins with countdowns, the Deeprun Tram, your hearthstone and class teleports, all in one route.
*   **Many stops:** add as many as you like and it sorts them into the fastest order.
*   **Find anyone and anything:** every NPC of your faction by name or service ("repair", "innkeeper"), items vendors sell, and Quick Find buttons for the nearest repair, vendor, innkeeper or flight master.
*   **Raise the roof:** hover a building or cave to see inside, with its NPCs.
*   **Quests:** quest areas on the map; double-click a quest to route to it.
*   **Dungeons and raids:** floor maps, bosses in order, and a stop at the right entrance.
*   **Your map, your way:** its own window, the game's world map or your minimap; any size and opacity; fades while you run, hides in combat.
*   **Controller support,** with an on-screen keyboard for search.
*   **Farming:** herbs and ore remembered across your characters, GatherMate2 import.
*   **Sharing:** TomTom `/way` import and route links in chat.
*   **Display only:** it never moves your character or clicks anything for you.

![Search Places on a controller: typing "repa" on the on-screen keyboard and the route to a repair NPC](https://azerothgps.com/press/controller-search-1312.gif)

## Getting started

1.  The map sits at the bottom of your screen (`/agps show` if it's hidden).
2.  **Double-click the map** to add a stop, then **Confirm Route** (or wait 5 seconds).
3.  Follow the line or the arrow.
4.  Open the flight map once at any flight master so it knows your flight paths.

You'll see about 38 "AzerothGPS map data" entries in your AddOn List: that's the routing grid, split by region so only what a route needs gets loaded. Keep them on.

## Come say hi

*   **[Discord](https://discord.gg/hHEguxVQFb):** questions, ideas and news.
*   **Bugs and bad routes:** the [report form](https://azerothgps.com/feedback/) or the Discord, with the zone and your start and destination coordinates (shown at the bottom of the map).

_Thanks to jigrobbulus, creator of **[OpenMap](https://www.curseforge.com/wow/addons/openmap)**, for open-sourcing the world map AzerothGPS builds on._

_AzerothGPS is a fan-made addon and is not affiliated with or endorsed by Blizzard Entertainment. World of Warcraft and Azeroth are trademarks of Blizzard Entertainment, Inc._
