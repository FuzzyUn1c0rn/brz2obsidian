# Development check receipts retain both disk and Git identities

Use Git's clean filters and line-ending policy to normalize paths for the
commit identity while hashing the exact working bytes separately. Applying
normalization through Git without updating the index gives the same commit
binding across Windows and WSL. Historical references use the attributes
effective at their own tree because fixture and normalization policies can
change. Ignore caller-supplied pytest arguments and plugins so the executed
selection matches the receipt's declared scope.
