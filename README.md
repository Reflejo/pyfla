# pyFLA

pyFLA is a library to hack CS5/CS6 uncompressed .fla files (merge, get elements…). ALERT: Hack!

Some randome example:

```python
>>> fla = FLA.fromfile('Element1.fla') + FLA.fromfile('Element2.fla')
>>> fla.save('Merged.fla')
```