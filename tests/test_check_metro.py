"""Pruebas sin red: se simulan la respuesta de Metro y los envíos."""
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import check_metro as cm  # noqa: E402

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "estado_normal.json").read_text(encoding="utf-8"))


def con_estacion(data, linea, codigo, estado, desc, desc_app, mensaje=""):
    d = copy.deepcopy(data)
    for est in d[linea]["estaciones"]:
        if est["codigo"] == codigo:
            est.update(estado=estado, descripcion=desc, descripcion_app=desc_app, mensaje=mensaje)
    return d


CERRADA = con_estacion(FIXTURE, "l1", "UC", "4", "Estación Cerrada", "Cerrada", "Por manifestación")


class TestNormalizarYComparar(unittest.TestCase):
    def test_normaliza_estructura_real(self):
        snap = cm.normalizar(FIXTURE)
        self.assertIn("l1:SP", snap["estaciones"])
        self.assertEqual(snap["lineas"]["l4a"]["nombre"], "Línea 4A")

    def test_formato_inesperado_falla(self):
        with self.assertRaises(cm.ErrorConsulta):
            cm.normalizar({"l1": {"estado": "1"}})
        with self.assertRaises(cm.ErrorConsulta):
            cm.normalizar([])

    def test_detecta_cierre_y_reapertura(self):
        normal, cerrada = cm.normalizar(FIXTURE), cm.normalizar(CERRADA)
        cierre = cm.comparar(normal, cerrada)
        self.assertEqual([(c["clave"], c["accion"]) for c in cierre], [("l1:UC", "incidencia")])
        reapertura = cm.comparar(cerrada, normal)
        self.assertEqual([(c["clave"], c["accion"]) for c in reapertura], [("l1:UC", "reabierta")])
        self.assertEqual(cm.comparar(normal, normal), [])

    def test_mensaje_escapa_html(self):
        d = con_estacion(FIXTURE, "l1", "UC", "2", "Accesos <parciales>", "Acceso & salida", "a < b")
        msg = cm.formatear_cambios(cm.comparar(cm.normalizar(FIXTURE), cm.normalizar(d)))
        self.assertIn("Acceso &amp; salida", msg)
        self.assertIn("a &lt; b", msg)
        self.assertNotIn("<parciales>", msg)

    def test_dividir_respeta_limite(self):
        bloques = cm.dividir("\n".join(["x" * 50] * 200), 400)
        self.assertTrue(all(len(b) <= 400 for b in bloques))
        self.assertEqual(sum(b.count("x") for b in bloques), 50 * 200)


class TestFlujo(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ruta = Path(self.tmp.name) / "estado.json"

    def tearDown(self):
        self.tmp.cleanup()

    def correr(self, respuesta):
        efecto = respuesta if isinstance(respuesta, Exception) else None
        with mock.patch.object(cm, "descargar_estado", return_value=respuesta, side_effect=efecto), \
             mock.patch.object(cm, "enviar", return_value=["telegram"]) as env, \
             mock.patch("builtins.print"):
            codigo = cm.verificar(self.ruta)
        return codigo, env

    def test_primera_vez_no_alerta(self):
        codigo, env = self.correr(FIXTURE)
        self.assertEqual(codigo, 0)
        env.assert_not_called()
        self.assertTrue(self.ruta.exists())

    def test_alerta_una_sola_vez_por_cambio(self):
        self.correr(FIXTURE)
        _, env = self.correr(CERRADA)
        self.assertEqual(env.call_count, 1)
        _, env = self.correr(CERRADA)  # sigue cerrada: sin spam
        env.assert_not_called()
        _, env = self.correr(FIXTURE)  # reabre
        self.assertEqual(env.call_count, 1)
        self.assertIn("Normalizado", env.call_args[0][0])

    def test_si_falla_el_envio_reintenta_despues(self):
        self.correr(FIXTURE)
        with mock.patch.object(cm, "descargar_estado", return_value=CERRADA), \
             mock.patch.object(cm, "enviar", side_effect=RuntimeError("HTTP 400")), \
             mock.patch("builtins.print"):
            self.assertEqual(cm.verificar(self.ruta), 1)
        _, env = self.correr(CERRADA)
        self.assertEqual(env.call_count, 1)

    def test_fallos_de_consulta_avisan_solo_al_tercero(self):
        self.correr(FIXTURE)
        codigos, envios = [], []
        for _ in range(5):
            c, env = self.correr(cm.ErrorConsulta("timeout"))
            codigos.append(c)
            envios.append(env.call_count)
        self.assertEqual(codigos, [0, 0, 1, 0, 0])
        self.assertEqual(envios, [0, 0, 1, 0, 0])
        _, env = self.correr(FIXTURE)  # recuperación
        self.assertIn("volvió a funcionar", env.call_args[0][0])

    def test_registra_codigos_vistos(self):
        self.correr(FIXTURE)
        self.correr(CERRADA)
        guardado = json.loads(self.ruta.read_text(encoding="utf-8"))
        self.assertEqual(guardado["codigos_vistos"]["4"], "Estación Cerrada")


class TestEnvio(unittest.TestCase):
    def test_sin_canales_imprime(self):
        with mock.patch.dict("os.environ", {}, clear=True), mock.patch("builtins.print") as p:
            self.assertEqual(cm.enviar("<b>hola</b>"), [])
        p.assert_called_once()

    def test_discord_convierte_formato(self):
        md = cm.html_a_markdown_discord('<b>L1</b> <i>x</i> <a href="https://a.b">ver</a> &amp;')
        self.assertEqual(md, "**L1** *x* [ver](https://a.b) &")


if __name__ == "__main__":
    unittest.main()
