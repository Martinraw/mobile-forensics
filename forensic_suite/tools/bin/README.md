# Bundled tool binaries

Drop platform-specific executables here. The app looks them up by
`platform.system().lower()` before falling back to your system `PATH`.

    tools/bin/
      windows/   phoneinfoga.exe
      linux/     phoneinfoga
      darwin/    phoneinfoga   (macOS)

## PhoneInfoga install

- Download a release: https://github.com/sundowndev/phoneinfoga/releases
- Then copy the binary into the appropriate `tools/bin/<os>/` folder.

Binaries are **not** committed to Git.