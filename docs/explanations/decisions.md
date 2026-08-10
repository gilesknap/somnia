# Architectural Decision Records

Architectural decisions are made throughout a project's lifetime. As a way of keeping track of these decisions, we record these decisions in Architecture Decision Records (ADRs) listed below.

```{toctree}
:glob: true
:maxdepth: 1

decisions/*
```

A record here is usually amended in place rather than superseded by a later
one, so **read the Status section first**: it says whether anything below it
has been withdrawn, and points at the amendment or the record that did it.
Records 3, 4 and 5 all carry amendments, and record 3 carries a retraction — a
claim it made about the handset that turned out to have been checked only one
way. The retraction is kept beside the claim on purpose. A decision record that
quietly loses its mistakes is a record of what we would like to have decided.

Record 10 amends 4 and 6 the same way, in one particular: both argue partly
from a high-water mark that no longer exists, and both keep their conclusions.

Record 9 is the exception that makes the rule worth stating. Dropping
Audiobookshelf could have been done by editing it out of records 3 and 7, and
that would have left record 3 arguing at length against a thing it never
mentions. So it is its own record, and 3 and 7 say at the top of themselves
which of their clauses it takes away.

For more information on ADRs see this [blog by Michael Nygard](http://thinkrelevance.com/blog/2011/11/15/documenting-architecture-decisions).
