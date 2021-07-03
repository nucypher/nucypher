This directory collects "newsfragments": short files that each contain
a snippet of ReST-formatted text that will be added to the next
release notes. This should be a description of aspects of the change
(if any) that are relevant to users. It contrasts with the
commit message and PR description, which are descriptions of the change
relevant to people working on the code itself.

The pull request (PR) number should be included in the newsfragment file name. Each newsfragment file
should be named `<PR_NUMBER>.<TYPE>.rst`, where `<TYPE>` is one of:

* `feature` - features
* `bugfix` - bugfixes
* `doc` - documentation
* `removal` - deprecations and removals
* `misc` - other

For example: `123.feature.rst`, `456.bugfix.rst`, `789.doc.rst`.

There can be multiple newsfragment files of different types for the same PR
e.g. `123.feature.rst` and `123.removal.rst`.

Along with the required PR newsfragment file (enforced by a GitHub Action),
additional newsfragment files for issues linked to the PR can optionally be
included by following the same naming convention above, and
using `<ISSUE_NUMBER>` instead of `<PR_NUMBER>`.

Note that the `towncrier` tool will automatically
reflow your text, so don't try to do any fancy formatting. Run
`towncrier --draft` to preview what the release notes entry
will look like in the final release notes.
