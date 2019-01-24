# Contributing

![NuCypher Unicorn](https://cdn-images-1.medium.com/max/800/1*J31AEMsTP6o_E5QOohn0Hw.png)

## Development Installation

## Running the Tests

## Issuing a New Release with `bumpversion`

1. Ensure your local tree has no uncommitted changes
2. Run `$ bumpversion devnum`
3. Ensure you have the intended history and tag: `git log`
4. Push the resulting tagged commit to the originating remote, and directly upstream `$ git push origin <TAG> && git push upstream <TAG>`
5. Monitor the triggered deployment build on circleCI for manual approval
