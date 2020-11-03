This directory collects "newsfragments": short files that each contain
a snippet of ReST-formatted text that will be added to the next
release notes. This should be a description of aspects of the change
(if any) that are relevant to users. (This contrasts with the
commit message and PR description, which are a description of the change as
relevant to people working on the code itself.)

The pull request (PR) number should be used for the newsfragment file. Each file
should be named `<PR_NUMBER>.<TYPE>.rst`, where `<TYPE>` is one of:

* `feature`
* `bugfix`
* `doc`
* `misc`

For example: `123.feature.rst`, `456.bugfix.rst`

Along with the required PR newsfragment file (enforced by a GitHub Action),
additional newsfragment files for issues linked to the PR can optionally be
included by following the same naming convention above, and
using `<ISSUE_NUMBER>` instead of `<PR_NUMBER>`.

Note that the `towncrier` tool will automatically
reflow your text, so don't try to do any fancy formatting. Run
`towncrier --draft` to get a preview of what the release notes entry
will look like in the final release notes.
