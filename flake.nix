{
  description = "Vial - Open-source GUI for configuring QMK keyboards";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-parts.url = "github:hercules-ci/flake-parts";
  };

  outputs =
    inputs@{ flake-parts, ... }:
    flake-parts.lib.mkFlake { inherit inputs; } {
      systems = [
        "x86_64-linux"
        "aarch64-linux"
      ];

      perSystem =
        { pkgs, self', ... }:
        let
          pythonEnv = pkgs.python3.withPackages (
            ps: with ps; [
              pyside6
              qtpy
              hidapi
              simpleeval
              certifi
            ]
          );
        in
        {
          packages = {
            default = self'.packages.vial;

            vial = pkgs.stdenv.mkDerivation {
              pname = "vial";
              version = "0.8.0-ilc";

              src = ./.;

              nativeBuildInputs = with pkgs; [
                qt6.wrapQtAppsHook
                makeWrapper
              ];

              buildInputs = with pkgs; [
                qt6.qtbase
                libusb1
              ];

              qtWrapperArgs = [
                "--unset QT_STYLE_OVERRIDE"
              ];

              propagatedBuildInputs = [ pythonEnv ];

              dontBuild = true;

              installPhase = ''
                runHook preInstall

                mkdir -p $out/share/vial
                cp -r src/main/python/* $out/share/vial/
                cp -r src/main/resources/base/* $out/share/vial/

                # Create build_settings.json in the resource directory
                cat > $out/share/vial/build_settings.json << SETTINGS
                {
                    "app_name": "Vial",
                    "author": "ilc",
                    "version": "0.8.0-ilc"
                }
                SETTINGS

                # Patch app_context.py to use our Nix-compatible paths
                substituteInPlace $out/share/vial/app_context.py \
                  --replace-fail "return os.path.normpath(os.path.join(script_dir, '..', '..', 'build', 'settings', 'base.json'))" \
                                 "return os.path.join(script_dir, 'build_settings.json')" \
                  --replace-fail "return os.path.normpath(os.path.join(script_dir, '..', 'resources', 'base'))" \
                                 "return script_dir"

                # Create launcher script
                mkdir -p $out/bin
                makeWrapper ${pythonEnv}/bin/python $out/bin/vial \
                  --add-flags "$out/share/vial/main.py"

                # udev rules
                mkdir -p $out/etc/udev/rules.d
                echo 'KERNEL=="hidraw*", SUBSYSTEM=="hidraw", MODE="0666", TAG+="uaccess", TAG+="udev-acl"' > $out/etc/udev/rules.d/92-vial.rules

                # Desktop entry
                mkdir -p $out/share/applications
                cat > $out/share/applications/vial.desktop << DESKTOP
                [Desktop Entry]
                Name=Vial
                Comment=Configure your QMK keyboard
                Exec=$out/bin/vial
                Icon=vial
                Terminal=false
                Type=Application
                Categories=Utility;
                DESKTOP

                # Icons (if available)
                if [ -d "src/main/icons" ]; then
                  mkdir -p $out/share/icons
                  cp -r src/main/icons/* $out/share/icons/
                fi

                runHook postInstall
              '';

              dontWrapQtApps = false;

              preFixup = ''
                wrapQtApp $out/bin/vial
              '';

              meta = with pkgs.lib; {
                description = "Open-source GUI for configuring QMK keyboards in real time";
                homepage = "https://get.vial.today";
                license = licenses.gpl2Plus;
                platforms = platforms.linux;
                mainProgram = "vial";
              };
            };
          };

          devShells.default = pkgs.mkShell {
            packages = [
              pythonEnv
              pkgs.qt6.qtbase
            ];
          };
        };
    };
}
