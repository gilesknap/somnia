# 7. A second library, under the same ids

Date: 2026-08-08

## Status

Accepted

## Context

Project Gutenberg Australia holds books Project Gutenberg does not. The two
clear their books against different countries' copyright law — Australia's is
life+70 from the author's death, America's is 95 years from publication — so
the collections barely overlap. Matching all 4,384 Australian titles against
the 77,820 in the Gutenberg dump on title and author finds around 650 in both.
The rest is roughly four fifths of the smaller library, and it is not marginal:
it holds every Orwell novel, *Tender is the Night*, late Woolf and Chesterton,
and several thousand pulp titles nobody else has transcribed.

somnia identifies a book by one integer. That `gid` is the primary key of
`books`, the foreign key of `chapters` and `chunks`, the unique key of a live
queue row, a path segment in four HTTP routes, the thing a saved position is
saved against, and the number the page holds in a variable all night. Adding a
second library means either that integer stops being sufficient, or it does
not.

Three things about the Australian library are not true of the other one. There
is no CSV dump and no API — the catalog is one plain text file meant for a
person to read. A book's address cannot be computed from its id, the way
Gutenberg's always can. And it is finished: no new books since 31 December
2024.

## Decision

**One `gid` space, offset.** Australian ids are `900,000,000` plus the book's
address — two digits of directory and seven of filename. Gutenberg is at 78,000
after fifty years, so the ranges cannot meet. Both halves of the address go in
because the file stem alone is not unique: `1000621` is *The Last Lemurian*
under `ebooks11` and *A Mummer's Throne* under `ebooks10`.

**One `catalog` table**, holding both libraries, because the question the page
asks is "what can I listen to tonight" and that has one answer. Which library a
result came from is read back off its id rather than stored, so there is one
fact and not two that can drift.

**A new `catalog_urls` table** mapping gid to address, written at import. Not
derived: sixty-nine of the four thousand break even the loose naming rule, so a
computed URL would 404 at the front of the queue, hours after the press, and
read as "Gutenberg does not have this book".

**One parser.** Australia marks its books up the same way — a heading per
chapter, a `<p>` per paragraph — and `parse_book_html` handled them unaltered
the first time it was tried. Only what wraps them differs, which is one
function that cuts on the HTML comments fencing the site banner and footer.

## Consequences

Nothing downstream of the catalog learns that there are two libraries. The
queue, the player, the audio routes, the semantic index and every saved
position keep the column they already have, and no migration touches them.

`catalog_urls` is a new table, so `CREATE TABLE IF NOT EXISTS` really does reach
an existing database. A missing row means Gutenberg proper, which is exactly
what every database that predates this table already meant, so there is nothing
to backfill and no window in which search returns nothing.

The catalog is rebuilt from both lists at once. A library that is unreachable
costs the whole update rather than half of one, and `somnia catalog-update`
now makes two requests instead of one.

Nine-digit ids appear in the CLI, in URLs and in the page. They are ugly and
they are load-bearing: the id says which library the book is from.

**somnia does not check whether an Australian book is public domain where the
listener is, and cannot** — the index carries no author death dates. The
library is cleared for Australia only and says so itself. That check is the
reader's.
