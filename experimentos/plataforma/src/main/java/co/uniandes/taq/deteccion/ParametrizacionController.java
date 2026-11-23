package co.uniandes.taq.deteccion;

import java.util.Map;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/** API de componente_parametrizacion: consultar y cambiar las reglas antifraude. */
@RestController
@RequestMapping("/parametros")
@ConditionalOnProperty(name = "taq.role", havingValue = "deteccion")
public class ParametrizacionController {
    private final Parametros parametros;
    public ParametrizacionController(Parametros parametros) { this.parametros = parametros; }

    @GetMapping
    public Map<String, Object> consultar() { return parametros.reglas().mapa(); }

    @PutMapping
    public ResponseEntity<Map<String, Object>> cambiar(@RequestBody Map<String, Object> cuerpo) {
        try { return ResponseEntity.ok(parametros.cambiar(cuerpo)); }
        catch (Exception e) { return ResponseEntity.badRequest().body(Map.of("error", String.valueOf(e.getMessage()))); }
    }
}
