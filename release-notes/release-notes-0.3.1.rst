##############
Podfetch 0.3.1
##############
Changes in **podfetch 0.3.1**:

- Index files are now in JSON format.
- Filenames for downloaded episodes are coerced to ascii.
- ``ls`` command can list episodes for a subscription
- ``update`` command has an option to ``--force`` downloading
  new episodes.
- Fixed error where temporary files for downloads were not deleted
  properly which caused the ``/tmp`` directory to run out of space
  if many episodes were downloaded in a single update run.
