package co.uniandes.taq.bloqueo;

import java.util.List;
import java.util.Map;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/bloqueo")
@ConditionalOnProperty(name = "taq.role", havingValue = "bloqueo")
public class BloqueoController {
    private final BdBloqueo bd;
    public BloqueoController(BdBloqueo bd) { this.bd = bd; }

    @SuppressWarnings("unchecked")
    private static List<Integer> asientos(Map<String, Object> c) {
        return ((List<Number>) c.get("asientos")).stream().map(Number::intValue).toList();
    }

    @PostMapping("/bloquear")
    public Map<String, Object> bloquear(@RequestBody Map<String, Object> c) throws Exception {
        return bd.bloquear((String) c.get("solicitudId"), (String) c.get("comprador"), asientos(c));
    }

    @PostMapping("/vender")
    public Map<String, Object> vender(@RequestBody Map<String, Object> c) throws Exception {
        return bd.vender((String) c.get("solicitudId"), (String) c.get("comprador"), asientos(c));
    }

    /** EXP-3: libera todo lo que retiene un comprador (S-2) y, con revocar=true, rechaza sus reservas nuevas. */
    @PostMapping("/liberar-comprador")
    public Map<String, Object> liberarComprador(@RequestBody Map<String, Object> c) throws Exception {
        return bd.liberarComprador((String) c.get("comprador"), Boolean.TRUE.equals(c.get("revocar")));
    }

    /** EXP-3: asientos retenidos por cada comprador de la lista (separados por coma). */
    @GetMapping("/retenidos")
    public Map<String, Object> retenidos(@RequestParam String compradores) throws Exception {
        return bd.retenidos(List.of(compradores.split(",")));
    }

    @GetMapping("/estado")
    public Map<String, Object> estado() throws Exception { return bd.estado(); }

    @GetMapping("/auditoria")
    public List<Map<String, Object>> auditoria() throws Exception { return bd.auditoria(); }
}
