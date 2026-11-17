# Contributing to AzerothGPS

Thanks for helping. AzerothGPS is a car-GPS style navigation addon for World of Warcraft: Forever. This repository
is where players and developers can send fixes and improvements. Please read this page before you open a pull
request.

## How changes reach the game

1. You open a pull request against `main` in this repository.
2. The tests run automatically (see below). A maintainer reviews the change and may ask for changes.
3. When it is accepted, it is merged into `main` here.
4. The maintainers then bring accepted changes into their own copy of AzerothGPS. There a change may be reworked,
   combined with other work, or held back before it ships. It goes through more testing, including in game.
5. **Releases come only from the maintainers.** Nothing in this repository builds, publishes or uploads the addon.
   A merged pull request is not a release, and it may be some time before it ships.

From time to time the maintainers bring this repository's `main` up to date with their latest code, through a
pull request titled "Sync from the maintainers' main". After one lands, update your branch before you continue:

```bash
git fetch upstream
git rebase upstream/main
```

(`upstream` is this repository; `origin` is your fork.)

## Setting up

You need Python 3.12 or newer (the tests run on 3.14) and Git.

```bash
git clone https://github.com/<you>/AzerothGPS-Community.git
cd AzerothGPS-Community
python -m venv .venv
```

Activate the environment (`.venv\Scripts\activate` on Windows, `source .venv/bin/activate` elsewhere), then:

```bash
python -m pip install -e "app[dev]"
```

The `dev` extras bring pytest, pytest-xdist and lupa. The Lua tests run the addon's code in Lua 5.1 through lupa.
Without it they are skipped.

## Running the tests

From the `app` folder:

```bash
cd app
python -P -m pytest -q
```

To use several CPU cores:

```bash
python -P -m pytest -q -n auto --dist loadfile
```

A few tests read a local World of Warcraft: Forever install and are skipped without one. That is expected.

Every pull request also runs a Lua syntax check with [luacheck](https://github.com/lunarmodules/luacheck):

```bash
luacheck addon --no-config --std lua51 --codes --only 0
```

## What makes a good pull request

- **One change per pull request,** with a short description of what it fixes or adds and how you checked it.
- **Add or update a test** for the behavior you change. A bug that comes back gets a test that fails on it.
- **Keep the addon display-only.** AzerothGPS must follow Blizzard's UI Add-On Development Policy: no automation
  of player actions, no Blizzard assets beyond what the game already provides, readable code, free to use.
- **No network or shell code** in the developer tools unless it is clearly needed and explained. Changes to
  workflows, scripts, the `.toc` file or packaging files get an extra careful review.
- **Don't edit the generated data** in `addon/AzerothGPS/Data/` by hand when a generator exists (`agps`
  commands in `app/azerothgps/`). Say in the pull request if you had to.
- **American spelling** in player-facing text and docs (color, center, gray, behavior).
- **Never include personal information:** no real names, email addresses, account or character names, or paths
  from your own computer, in code, comments, commit messages or screenshots.

## Licensing of contributions

AzerothGPS is not open-source licensed: see [LICENSE](LICENSE). By opening a pull request you confirm that the
contribution is your own work (or you have the right to submit it) and you grant the AzerothGPS maintainers a
perpetual, worldwide, royalty-free, irrevocable license to use, modify, relicense and distribute it as part of
AzerothGPS. You keep the copyright to your own contribution. Contributors whose changes ship are credited in the
commit that brings them in (`Co-authored-by`).

## Reporting problems

- Bugs and road data: [azerothgps.com](https://azerothgps.com) has the report form and the guide.
- Security problems: please don't open a public issue. See [SECURITY.md](SECURITY.md).

## Conduct

Be kind and constructive. Reviews are about the code, not the person. The maintainers may close pull requests or
block accounts that are abusive or spam.
