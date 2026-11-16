from django.core.exceptions import ValidationError


def validar_cedula(cedula):
    """
    Valida una cédula ecuatoriana con el algoritmo de módulo 10:
    - 10 dígitos; los dos primeros (provincia) entre 01 y 24, o 30.
    - El tercer dígito es menor que 6 (persona natural).
    - El último dígito es el verificador.
    """
    if not (cedula.isdigit() and len(cedula) == 10):
        raise ValidationError('La cédula debe tener exactamente 10 dígitos.')

    provincia = int(cedula[:2])
    if not (1 <= provincia <= 24 or provincia == 30) or int(cedula[2]) >= 6:
        raise ValidationError('La cédula no es válida.')

    coeficientes = [2, 1, 2, 1, 2, 1, 2, 1, 2]
    suma = 0
    for digito, coef in zip(cedula[:9], coeficientes):
        producto = int(digito) * coef
        suma += producto - 9 if producto > 9 else producto

    verificador = (10 - suma % 10) % 10
    if verificador != int(cedula[9]):
        raise ValidationError('La cédula no es válida (dígito verificador incorrecto).')
