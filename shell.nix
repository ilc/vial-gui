{ pkgs ? import <nixpkgs> {} }:

pkgs.mkShell {
  buildInputs = with pkgs; [
    (python312.withPackages (ps: with ps; [
      qtpy
      pyside6
      pytest
      pytest-qt
      hidapi
      keyboard
      simpleeval
      certifi
    ]))

    # HID access
    hidapi
    libusb1
  ];

  shellHook = ''
    export PYTHONPATH="src/main/python:$PYTHONPATH"
    echo "Run: python src/main/python/main.py"
    echo "Test: pytest src/main/python/test/"
  '';
}
