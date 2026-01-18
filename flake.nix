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
              pyqt5
              hidapi
              simpleeval
              certifi
            ]
          );

          # fbs_runtime shim files
          fbsRuntimeInit = pkgs.writeText "fbs_runtime__init__.py" ''
            # fbs_runtime shim for running without fbs
          '';

          fbsAppContextInit = pkgs.writeText "fbs_runtime_application_context__init__.py" ''
            # fbs_runtime.application_context shim
            from functools import cached_property

            def is_frozen():
                return False
          '';

          fbsAppContextPyQt5 = pkgs.writeText "fbs_runtime_application_context_PyQt5.py" ''
            # fbs_runtime.application_context.PyQt5 shim
            import sys
            import os
            from functools import lru_cache
            from PyQt5 import QtWidgets, QtGui

            def cached_property(getter):
                return property(lru_cache()(getter))

            class ApplicationContext:
                def __init__(self):
                    # Access app to ensure QApplication is created first
                    self.app

                @cached_property
                def app(self):
                    result = QtWidgets.QApplication(sys.argv)
                    result.setApplicationName(self.build_settings["app_name"])
                    result.setApplicationVersion(self.build_settings["version"])
                    return result

                @cached_property
                def build_settings(self):
                    return {
                        "app_name": "Vial",
                        "version": "0.8.0-ilc",
                    }

                def get_resource(self, *path):
                    # Resources are in the share/vial directory (where main.py is)
                    # __file__ is fbs_runtime/application_context/PyQt5.py
                    # So we need to go up 3 levels to get to share/vial
                    base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
                    return os.path.join(base, *path)
          '';
        in
        {
          packages = {
            default = self'.packages.vial;

            vial = pkgs.stdenv.mkDerivation {
              pname = "vial";
              version = "0.8.0-ilc";

              src = ./.;

              nativeBuildInputs = with pkgs; [
                qt5.wrapQtAppsHook
                makeWrapper
              ];

              buildInputs = with pkgs; [
                qt5.qtbase
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

                # Create fbs_runtime shim
                mkdir -p $out/share/vial/fbs_runtime/application_context
                cp ${fbsRuntimeInit} $out/share/vial/fbs_runtime/__init__.py
                cp ${fbsAppContextInit} $out/share/vial/fbs_runtime/application_context/__init__.py
                cp ${fbsAppContextPyQt5} $out/share/vial/fbs_runtime/application_context/PyQt5.py

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
              pkgs.qt5.qtbase
            ];

            QT_QPA_PLATFORM_PLUGIN_PATH = "${pkgs.qt5.qtbase.bin}/lib/qt-${pkgs.qt5.qtbase.version}/plugins";
          };
        };
    };
}
