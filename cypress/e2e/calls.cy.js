describe("Chamados de manutenção", () => {
  const professorEmail = Cypress.env("PROFESSOR_EMAIL") || "professor@senai.br";
  const professorPassword = Cypress.env("PROFESSOR_PASSWORD") || "Prof@123456";
  const adminEmail = Cypress.env("ADMIN_EMAIL") || "admin@senai.br";
  const adminPassword = Cypress.env("ADMIN_PASSWORD") || "Admin@123456";

  it("professor abre um chamado para um equipamento", () => {
    cy.uiLogin(professorEmail, professorPassword);

    cy.contains("a", "Novo chamado").click();
    cy.url().should("include", "/chamados/novo");

    // Seleciona equipamento (Fresa 02 existe nos dados iniciais do schema).
    cy.get("#equipamento").select("Fresa 02");

    // Tipo de manutenção é carregado dinamicamente via JS após escolher o equipamento.
    cy.get("#problema_tipo").should("not.be.disabled");
    cy.get("#problema_tipo").select("Manutenção preventiva geral da fresa");

    cy.get("#descricao")
      .type("Vibração anormal no eixo principal da fresa durante o funcionamento.");

    cy.get("#prioridade").select("Alta");

    cy.get('button[type="submit"]').contains("Abrir chamado").click();

    // Redireciona para a lista de chamados com aviso de sucesso.
    cy.url().should("include", "/chamados");
    cy.contains("Chamado registrado com sucesso").should("be.visible");

    // O chamado recém-criado deve aparecer na lista.
    cy.contains("Fresa 02").should("exist");
    cy.contains("Alta").should("exist");

    cy.uiLogout();
  });

  it("administrador aprova um chamado aberto e gera ordem de serviço", () => {
    // Cria um chamado como professor.
    cy.uiLogin(professorEmail, professorPassword);
    cy.contains("a", "Novo chamado").click();
    cy.get("#equipamento").select("Torno 01");
    cy.get("#problema_tipo").should("not.be.disabled");
    cy.get("#problema_tipo").select("Manutenção preventiva geral do torno");
    cy.get("#descricao").type("Ruído metálico na caixa de engrenagens do torno.");
    cy.get("#prioridade").select("Média");
    cy.get('button[type="submit"]').contains("Abrir chamado").click();
    cy.contains("Chamado registrado com sucesso").should("be.visible");

    // Captura o número do chamado da lista.
    cy.contains("Torno 01").closest("tr").then(($row) => {
      const callNumber = $row.find("a.table__id").text().trim();
      cy.wrap(callNumber).as("callNumber");
    });

    cy.uiLogout();

    // Aprova como administrador.
    cy.uiLogin(adminEmail, adminPassword);
    cy.contains("a", "Chamados").click();
    cy.get("@callNumber").then((callNumber) => {
      cy.contains(callNumber).closest("tr").within(() => {
        // O botão de aprovar só aparece no detalhe; acessa o detalhe primeiro.
        cy.get("a.table__id").click();
      });
    });

    cy.contains("Aprovar e gerar OS").click();
    cy.contains("Ordem de serviço gerada").should("be.visible");
    cy.contains("Ordem de serviço").should("exist");

    cy.uiLogout();
  });
});
