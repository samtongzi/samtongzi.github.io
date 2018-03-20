#!/bin/bash
dpkg-scanpackages -m . /deb/null > Packages
rm Packages.bz2
bzip2 Packages

git add --all
git commit -m "add debs"
git push origin master
