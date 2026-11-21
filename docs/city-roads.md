# City roads without the spiderweb (issue #829)

The capitals' roads (`Data/Capitals.lua`) are the road skeleton of the city models' floors. Over a wide open floor
a skeleton is a web of branches and zigzags, and routes followed it. `agps city-roads --city <name> --write`
(`app/azerothgps/cityroads.py`) post-processes a city's shipped roads over our own Recast mesh of it
(`agps navmesh build`, `data/navmesh/`; the mesh is a dev tool's data and never ships):

1. **Straight roads.** Each plain road is walked over the mesh at its own heights, then string-pulled: a bend goes
   wherever the straight line between its neighbors stays on the mesh, at the road's floor (never up onto a bridge or
   across a gap). Roads the mesh can't walk keep their points and are listed below.
2. **No web.** Plain roads, shortest first, are kept only when the roads kept so far don't already join their ends
   within 1.25 times their length (+4 yd). Joins to the land, drops, lifts, stairs and swims are never touched. Dead
   ends under 8 yd go: a stop there is reached by a dotted leg off the road.
3. **Fewer pieces.** Two plain roads meeting at a node nothing else uses become one when the heights the game reads
   along it (straight between its ends) stay within 1 yd of the node's and 2 yd of the floor. Nodes within 25 yd of a
   city place stay (stops get onto the roads there).

Undercity's roads are in `Data/Cities.lua`, a format of its own: next.

## Orgrimmar

| | roads | plain | nodes | points | yards |
|---|---|---|---|---|---|
| before | 696 | 639 | 579 | 2178 | 11389 |
| after | 616 | 559 | 509 | 1544 | 10763 |

Dropped 17 roads (web and stubs), joined 63 pairs into one.

Routes in the city (`agps city-roads --check`: from outside to each place at its height, and 150 trips between two
places, the Router as the addon runs it): 177 trips, 117,656 yd before and 115,745 after, 7,255 turns of more than
20 degrees before and 5,048 after; no way lost. Two trips are over 10% longer, both from the Mining Trainer: its way
onto the roads from inside its building now reaches a straightened road further round (77 to 104 yd to the Fishing
Trainer, 118 to 157 to the Engineering Trainer).

## Orgrimmar: roads to record in game

The mesh can't walk these roads at their heights (through a wall, over a gap, a floor the mesh left out, a door the
server spawns). They were left as they were. A road recorded in game over them wins.

| road | where (x, y) | heights (ends) | yd | why |
|---|---|---|---|---|
| 3 | 2207, -4739 | 68, 70 | 3 | it leaves the mesh |
| 30 | 2099, -4727 | 48, 40 | 27 | it leaves the mesh |
| 36 | 2059, -4645 | 48, 52 | 36 | it leaves the mesh |
| 46 | 2041, -4695 | 36, 26 | 22 | it leaves the mesh |
| 85 | 1907, -4423 | 62, 56 | 18 | it leaves the mesh |
| 88 | 1911, -4525 | 30, 24 | 34 | it leaves the mesh |
| 89 | 1909, -4531 | 30, 30 | 14 | it leaves the mesh |
| 134 | 1795, -4319 | -12, -10 | 18 | it leaves the mesh |
| 157 | 1737, -4335 | 32, 28 | 13 | it leaves the mesh |
| 168 | 1727, -4479 | 36, 32 | 16 | it leaves the mesh |
| 200 | 1635, -4107 | 36, 30 | 39 | it leaves the mesh |
| 221 | 1641, -4364 | 22, 30 | 24 | it leaves the mesh |
| 283 | 1419, -4355 | 26, 26 | 17 | it leaves the mesh |
| 286 | 1413, -4357 | 26, 26 | 20 | it leaves the mesh |
| 287 | 1415, -4413 | 20, 30 | 13 | its start is on no floor of the mesh at its height |
| 294 | 1391, -4391 | 28, 30 | 10 | it leaves the mesh |
| 295 | 1391, -4391 | 30, 30 | 14 | its start is on no floor of the mesh at its height |
| 298 | 1391, -4391 | 30, 30 | 12 | its start is on no floor of the mesh at its height |
| 326 | 1329, -4325 | 28, 30 | 12 | it leaves the mesh |
| 335 | 1823, -4231 | 40, 40 | 67 | it leaves the mesh |
| 339 | 1739, -4469 | 36, 34 | 14 | it leaves the mesh |
| 382 | 2155, -4795 | 68, 72 | 8 | it leaves the mesh |
| 386 | 2207, -4739 | 68, 70 | 3 | it leaves the mesh |
| 446 | 1679, -4263 | 32, 34 | 8 | it leaves the mesh |
| 456 | 1583, -4321 | 26, 22 | 6 | it leaves the mesh |
| 474 | 1685, -4287 | 32, 28 | 3 | it leaves the mesh |
| 480 | 1649, -4286 | 28, 32 | 20 | it leaves the mesh |
| 529 | 1649, -4389 | 30, 20 | 28 | it leaves the mesh |
| 533 | 2161, -4795 | 70, 68 | 6 | it leaves the mesh |
| 548 | 1829, -4499 | 46, 42 | 10 | it leaves the mesh |
| 553 | 1721, -4331 | 30, 24 | 7 | it leaves the mesh |
| 555 | 1716, -4328 | 28, 22 | 6 | it leaves the mesh |
| 560 | 1647, -4287 | 26, 32 | 8 | it leaves the mesh |
| 567 | 1585, -4279 | 42, 48 | 6 | it ends off its end's height |
| 573 | 1379, -4435 | 34, 30 | 1 | it leaves the mesh |
| 574 | 1380, -4386 | 24, 30 | 6 | it leaves the mesh |
| 575 | 1369, -4369 | 24, 26 | 11 | it ends off its end's height |
| 599 | 2151, -4739 | 68, 70 | 3 | it leaves the mesh |
| 603 | 2153, -4737 | 62, 70 | 17 | it leaves the mesh |
