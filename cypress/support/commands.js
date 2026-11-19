// Custom commands para os testes E2E do SENAI CMMS.
// Pré-requisito: servidor rodando em http://127.0.0.1:8000 e banco
// Supabase populado com os dados iniciais do supabase_schema.sql.

Cypress.Commands.add("uiLogin", (email, password) => {
  cy.visit("/login");
  cy.get('input[name="email"]').type(email);
  cy.get('input[name="password"]').type(password);
  cy.get('input[name="csrf_token"]').should("exist");
  cy.get('button[type="submit"]').contains("Entrar").click();
  cy.url().should("eq", `${Cypress.config("baseUrl")}/dashboard`);
});

Cypress.Commands.add("uiLogout", () => {
  cy.get('form[action="/logout"] button[type="submit"]').contains("Sair").click();
  cy.url().should("include", "/login");
});
