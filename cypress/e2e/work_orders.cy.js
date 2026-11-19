describe("Ordens de serviço (atendimento e conclusão)", () => {
  const technicianEmail = Cypress.env("TECNICO_EMAIL") || "tecnico@senai.br";
  const technicianPassword = Cypress.env("TECNICO_PASSWORD") || "Tecnico@123456";
  const adminEmail = Cypress.env("ADMIN_EMAIL") || "admin@senai.br";
  const adminPassword = Cypress.env("ADMIN_PASSWORD") || "Admin@123456";
  const professorEmail = Cypress.env("PROFESSOR_EMAIL") || "professor@senai.br";
  const professorPassword = Cypress.env("PROFESSOR_PASSWORD") || "Prof@123456";

  beforeEach(() => {
    // Garante que existe um técnico cadastrado; se não existir, o teste falha com mensagem clara.
    cy.request("GET", "/api/users").then((resp) => {
      const hasTech = resp.body.some((u) => u.email === technicianEmail && u.role === "tecnico");
      if (!hasTech) {
        throw new Error(
          `Técnico ${technicianEmail} não cadastrado no banco. Cadastre um usuário com perfil 'tecnico' antes de rodar este teste.`
        );
      }
    });
  });

  it("técnico conclui uma ordem de serviço atribuída com solução", () => {
    // Fluxo: professor abre chamado -> admin aprova e gera OS -> admin atribui ao técnico -> técnico conclui.

    // 1. Professor abre chamado.
    cy.uiLogin(professorEmail, professorPassword);
    cy.contains("a", "Novo chamado").click();
    cy.get("#equipamento").select("Sopradora 01");
    cy.get("#problema_tipo").should("not.be.disabled");
    cy.get("#problema_tipo").select("Manutenção preventiva geral da máquina de sopro");
    cy.get("#descricao").type("Falta de pressão no sistema de sopro da máquina.");
    cy.get("#prioridade").select("Alta");
    cy.get('button[type="submit"]').contains("Abrir chamado").click();
    cy.contains("Chamado registrado com sucesso").should("be.visible");
    cy.uiLogout();

    // 2. Admin aprova o chamado e gera OS via UI.
    cy.uiLogin(adminEmail, adminPassword);
    cy.contains("a", "Chamados").click();
    cy.contains("Sopradora 01").closest("tr").find("a.table__id").click();
    cy.contains("Aprovar e gerar OS").click();
    cy.contains("Ordem de serviço gerada").should("be.visible");

    // Pega o id da OS gerada via API para atribuição.
    let orderId;
    cy.request("GET", "/api/auth/csrf").then((csrfResp) => {
      const csrfToken = csrfResp.body.csrf_token;
      return cy.request("GET", "/api/work-orders").then((woResp) => {
        orderId = woResp.body[0].id;
        const callId = woResp.body[0].call_id;

        // Descobre o id do técnico.
        return cy.request("GET", "/api/users").then((usersResp) => {
          const technician = usersResp.body.find(
            (u) => u.email === technicianEmail && u.role === "tecnico"
          );
          expect(technician).to.exist;

          // Atribui a OS ao técnico via API.
          return cy.request({
            method: "POST",
            url: `/api/calls/${callId}/atribuicoes`,
            headers: { "x-csrf-token": csrfToken },
            body: { responsible_id: technician.id },
          });
        });
      });
    }).then(() => {
      cy.uiLogout();

      // 3. Técnico conclui a OS.
      cy.uiLogin(technicianEmail, technicianPassword);
      cy.contains("a", "Ordens de Serviço").click();
      cy.get("table tbody tr").first().find("a.table__id").click();
      cy.url().should("include", "/ordens-servico/detalhe");

      cy.get("#status").select("Concluída");
      cy.get("#solution")
        .type("Substituída a vedação do sistema pneumático e reajustada a pressão de sopro.");
      cy.get('button[type="submit"]').contains("Salvar atualização").click();
      cy.contains("Ordem atualizada").should("be.visible");
      cy.contains("Concluída").should("be.visible");

      cy.uiLogout();
    });
  });
});
