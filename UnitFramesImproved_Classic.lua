-- Stylers for the Classic family (Classic Era/Vanilla, and Classic progression: Wrath, Cata, Mists, ...)
-- Shared because these clients still use the pre-Dragonflight global-named frame templates,
-- unlike Retail which was rebuilt around nested PlayerFrameContent-style templates.
local HEALTH_BAR_TEXTURE_Y_DELTA = 18
local HEALTH_BAR_TEXT_Y_DELTA = 3
local MINUS_CLASSIFICATION_Y_SHIFT = -19

function UnitFramesImproved:Style_PlayerFrame()
	PlayerFrameHealthBar.healthbar = PlayerFrameHealthBar

  -- Set up some local variables
  local healthBar = PlayerFrameHealthBar
  local manaBar = PlayerFrameManaBar

  if (not InCombatLockdown()) then
		--healthBar.lockColor = true
		healthBar.capNumericDisplay = true
		healthBar:SetWidth(119)
		healthBar:SetHeight(29)
		UnitFramesImproved:OffsetAnchor(healthBar, 0, HEALTH_BAR_TEXTURE_Y_DELTA)

    -- Offset the healthbar texts to be a bit higher than Blizzard's defaults
		UnitFramesImproved:OffsetAnchor(healthBar.TextString, 0, HEALTH_BAR_TEXT_Y_DELTA)
		UnitFramesImproved:OffsetAnchor(healthBar.LeftText, 0, HEALTH_BAR_TEXT_Y_DELTA)
		UnitFramesImproved:OffsetAnchor(healthBar.RightText, 0, HEALTH_BAR_TEXT_Y_DELTA)

    -- Style the manabar fontstrings
    UnitFramesImproved:SetFontSize(healthBar.TextString, 14)
    UnitFramesImproved:SetFontSize(healthBar.LeftText, 14)
    UnitFramesImproved:SetFontSize(healthBar.RightText, 14)

    -- Set fonts sizes for PlayerFrameManabar
    UnitFramesImproved:SetFontSize(manaBar.TextString, 12)
    UnitFramesImproved:SetFontSize(manaBar.LeftText, 12)
    UnitFramesImproved:SetFontSize(manaBar.RightText, 12)
	end
	
  -- Set the player frame textures
	PlayerFrameTexture:SetTexture("Interface\\Addons\\UnitFramesImproved\\Textures\\UI-TargetingFrame")
	PlayerStatusTexture:SetTexture("Interface\\Addons\\UnitFramesImproved\\Textures\\UI-Player-Status")

  -- Status text hook (used by all the statusbars!)
  hooksecurefunc("TextStatusBar_UpdateTextStringWithValues", UnitFramesImproved_UpdateTextStringWithValues)

  -- Update the statusbar color to trigger it to show at load
	UnitFramesImproved:UpdateStatusBarColor(healthBar)
end

function UnitFramesImproved:Style_TargetFrame(frame)
  -- Exit early if the frame is nil, such as in Vanilla, where the FocusFrame doesn't exist. But the addon will anyway try to style it to keep the code common.
  if (not frame) then
    return
  end

  -- Set up some local variables
  local healthBar = frame.healthbar
  local manaBar = frame.manabar

  if (healthBar) then
    if (not healthBar.LeftText and not healthBar.TextString and not healthBar.RightText) then
      if (not InCombatLockdown()) then
        healthBar.TextString = UnitFramesImproved:CreateStatusBarText("Text", frame:GetName().."HealthBar", frame.textureFrame, "CENTER", -33, 4)
        healthBar.LeftText = UnitFramesImproved:CreateStatusBarText("TextLeft", frame:GetName().."HealthBar", frame.textureFrame, "LEFT", 25, 4)
        healthBar.RightText = UnitFramesImproved:CreateStatusBarText("TextRight", frame:GetName().."HealthBar", frame.textureFrame, "RIGHT", -93, 4)
      end
    else
      UnitFramesImproved:OffsetAnchor(healthBar.TextString, 0, HEALTH_BAR_TEXT_Y_DELTA)
      UnitFramesImproved:OffsetAnchor(healthBar.LeftText, 0, HEALTH_BAR_TEXT_Y_DELTA)
      UnitFramesImproved:OffsetAnchor(healthBar.RightText, 0, HEALTH_BAR_TEXT_Y_DELTA)
    end

    -- Style the manabar fontstrings
    if (healthBar.TextString) then
      UnitFramesImproved:SetFontSize(healthBar.TextString, 14)
      UnitFramesImproved:SetFontSize(healthBar.LeftText, 14)
      UnitFramesImproved:SetFontSize(healthBar.RightText, 14)
    end
  end

  -- Create and/or style the manaBar texts
  if (manaBar) then
    if (not manaBar.LeftText and not manaBar.TextString and not manaBar.RightText) then
      if (not InCombatLockdown()) then
        manaBar.TextString = UnitFramesImproved:CreateStatusBarText("Text", frame:GetName().."ManaBar", frame.textureFrame, "CENTER", -33, -12)
        manaBar.LeftText = UnitFramesImproved:CreateStatusBarText("TextLeft", frame:GetName().."ManaBar", frame.textureFrame, "LEFT", 25, -12)
        manaBar.RightText = UnitFramesImproved:CreateStatusBarText("TextRight", frame:GetName().."ManaBar", frame.textureFrame, "RIGHT", -93, -12)
      end
    end

    -- Style the manabar fontstrings
    if (manaBar.TextString) then
      UnitFramesImproved:SetFontSize(manaBar.TextString, 12)
      UnitFramesImproved:SetFontSize(manaBar.LeftText, 12)
      UnitFramesImproved:SetFontSize(manaBar.RightText, 12)
    end
  end

  -- Style healthbar
  healthBar.lockColor = true

  -- Get classification
  local classification = UnitClassification(frame.unit)

  -- Handle offsets
  local textX, textY = -50, 6
  if (healthBar.TextString) then
    local _, _, _, currentTextX, currentTextY = healthBar.TextString:GetPoint()
    textX = currentTextX
    textY = currentTextY
  end

  -- Set frame background settings
  frame.Background:SetHeight(frame.Background:GetHeight() + 2)
  frame.nameBackground:Hide();

  -- Handle based on minus classification? Whatever that is.
  if (classification == "minus") then
    healthBar:SetHeight(12)
    UnitFramesImproved:OffsetAnchor(healthBar, 0, HEALTH_BAR_TEXTURE_Y_DELTA + MINUS_CLASSIFICATION_Y_SHIFT)
    if (healthBar.TextString) then
      healthBar.TextString:SetPoint("CENTER",textX,textY - 2)
    end
    frame.deadText:SetPoint("CENTER",textX,textY - 2)
    UnitFramesImproved:OffsetAnchor(frame.Background, 0, -2)
  else
    healthBar:SetHeight(29);
    UnitFramesImproved:OffsetAnchor(healthBar, 0, HEALTH_BAR_TEXTURE_Y_DELTA)
    if (healthBar.TextString) then
      healthBar.TextString:SetPoint("CENTER",textX,textY)
    end
    frame.deadText:SetPoint("CENTER",textX,textY)
    UnitFramesImproved:OffsetAnchor(frame.Background, 0, -2)
  end

  -- Style frame based on
  local texture;
  if ( classification == "worldboss" or classification == "elite" ) then
    texture = "Interface\\Addons\\UnitFramesImproved\\Textures\\UI-TargetingFrame-Elite";
  elseif ( classification == "rareelite" ) then
    texture = "Interface\\Addons\\UnitFramesImproved\\Textures\\UI-TargetingFrame-Rare-Elite";
  elseif ( classification == "rare" ) then
    texture = "Interface\\Addons\\UnitFramesImproved\\Textures\\UI-TargetingFrame-Rare";
  end
  if ( texture ) then
    frame.borderTexture:SetTexture(texture);
  else
    if ( not (classification == "minus") ) then
      frame.borderTexture:SetTexture("Interface\\Addons\\UnitFramesImproved\\Textures\\UI-TargetingFrame");
    end
  end

  -- Style frame based on faction
  local factionGroup = UnitFactionGroup(frame.unit);
  if ( UnitIsPVPFreeForAll(frame.unit) ) then
    frame.pvpIcon:SetTexture("Interface\\TargetingFrame\\UI-PVP-FFA");
    frame.pvpIcon:Show();
  elseif ( factionGroup and UnitIsPVP(frame.unit) and UnitIsEnemy("player", frame.unit) ) then
    frame.pvpIcon:SetTexture("Interface\\TargetingFrame\\UI-PVP-FFA");
    frame.pvpIcon:Show();
  elseif ( factionGroup == "Alliance" or factionGroup == "Horde" ) then
    frame.pvpIcon:SetTexture("Interface\\TargetingFrame\\UI-PVP-"..factionGroup);
    frame.pvpIcon:Show();
  else
    frame.pvpIcon:Hide();
  end
end

function UnitFramesImproved:Style_ToTFrame(frame)
end
