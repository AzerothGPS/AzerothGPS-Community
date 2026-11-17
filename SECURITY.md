# Security policy

## Reporting a vulnerability

Please **don't open a public issue or pull request** for a security problem.

Report it privately through GitHub's private vulnerability reporting: open the repository's **Security** tab and
choose **Report a vulnerability**. Include what you found, how to reproduce it, and what it could affect.

We'll acknowledge the report as soon as we can, keep you posted while we look into it, and credit you when a fix
ships, unless you'd rather not be named.

## Scope

In scope:

- the addon in `addon/AzerothGPS` (for example, a chat link or shared route that could make another player's addon
  misbehave);
- the developer tools in `app/` (for example, reading a crafted file that leads to code running);
- this repository's GitHub Actions workflow.

Out of scope: World of Warcraft itself, other addons, and problems that need someone who already controls your
computer.

## Supported versions

Only the latest released version of AzerothGPS gets security fixes.
