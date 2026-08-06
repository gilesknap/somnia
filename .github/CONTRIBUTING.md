# Contribute to the project

Contributions and issues are most welcome! All issues and pull requests are
handled through [GitHub](https://github.com/gilesknap/somnia/issues). Also, please check for any existing issues before
filing a new one. If you have a great idea but it involves big changes, please
file a ticket before making a pull request! We want to make sure you don't spend
your time coding something that might not fit the scope of the project.

## Issue or Discussion?

Github also offers [discussions](https://github.com/gilesknap/somnia/discussions) as a place to ask questions and share ideas. If
your issue is open ended and it is not obvious when it can be "closed", please
raise it as a discussion instead.

## Code Coverage

While 100% code coverage does not make a library bug-free, it significantly
reduces the number of easily caught bugs! Please make sure coverage remains the
same or is improved by a pull request!

## The page has tests of its own

`tox` runs pytest, and pytest cannot see a line of `src/somnia/web/app.js` —
which is where most of somnia's behaviour now lives, because the page is the
player. That code has its own suite under `tests/web/`, written against node's
built-in test runner and a fake media element, so it needs no npm install and
no browser:

```
$ node --test                    # every *.test.mjs in the repo, in under a second
```

`pre-commit` runs it whenever the page or those tests change, so `tox -e
pre-commit` covers it too and CI runs it on every pull request. What it cannot
tell you is whether the audio decodes, whether a Range request really comes
back 206, or whether the lock screen follows a chapter boundary. Those are
properties of a handset and are checked in a real browser against a real
`somnia serve` — the how-to guide *Serve the chat page* ends with how.

## Developer Information

It is recommended that developers use a [vscode devcontainer](https://code.visualstudio.com/docs/devcontainers/containers). This repository contains configuration to set up a containerized development environment that suits its own needs.

This project was created using the [Diamond Light Source Copier Template](https://github.com/DiamondLightSource/python-copier-template) for Python projects.

For more information on common tasks like setting up a developer environment, running the tests, and setting a pre-commit hook, see the template's [How-to guides](https://diamondlightsource.github.io/python-copier-template/5.1.0/how-to.html).
