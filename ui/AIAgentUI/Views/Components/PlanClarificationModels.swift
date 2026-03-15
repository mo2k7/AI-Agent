//
//  PlanClarificationModels.swift
//  AIAgentUI
//

import Foundation

struct PlanClarificationOption: Identifiable {
    let id: String
    let key: String
    let text: String
}

struct PlanClarificationQuestion: Identifiable {
    let id: Int
    let number: Int
    let prompt: String
    let options: [PlanClarificationOption]
}

struct PlanClarificationPayload {
    let intro: String
    let questions: [PlanClarificationQuestion]
}
