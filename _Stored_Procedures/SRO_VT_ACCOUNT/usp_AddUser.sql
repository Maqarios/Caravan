USE [SRO_VT_ACCOUNT]
GO
SET
	ANSI_NULLS ON
GO
SET
	QUOTED_IDENTIFIER ON
GO
	ALTER PROCEDURE [dbo].[usp_AddUser] (
		@StrUserID varchar(25),
		@Password varchar(50),
		@SecPassword varchar(50),
		@FullName nvarchar(30),
		@Question nvarchar(50),
		@Answer nvarchar(100),
		@Sex char(2),
		@BirthDay datetime,
		@Province nvarchar(50),
		@Address nvarchar(100),
		@Phone varchar(20),
		@Mobile varchar(20),
		@Email varchar(50),
		@cid varchar(30),
		@RegIP varchar(15),
		@JID int OUTPUT
	) AS IF(
		not exists(
			SELECT
				JID
			from
				tb_user
			where
				StrUserID = @StrUserID
		)
	) BEGIN BEGIN TRANSACTION
INSERT INTO
	tb_User (
		StrUserID,
		Password,
		Name,
		Email,
		Sex,
		Certificate_num,
		Address,
		Phone,
		Mobile,
		sec_primary,
		sec_content,
		AccPlayTime,
		LatestUpdateTime_ToPlayTime,
		regtime,
		reg_ip,
		freetime
	)
VALUES
	(
		@StrUserID,
		@Password,
		@FullName,
		@Email,
		@Sex,
		@cid,
		@Address,
		@Phone,
		@Mobile,
		3,
		3,
		0,
		0,
		getDate(),
		@RegIP,
		0
	)
SET
	@JID = SCOPE_IDENTITY() --Select @JID = JID From tb_User where StrUserID = @StrUserID
INSERT INTO
	tb_Net2E (
		JID,
		StrUserID,
		Password,
		SecondPassword,
		Question,
		Answer,
		Name,
		Email,
		Sex,
		Certificate_num,
		Address,
		Phone,
		Mobile,
		cidtype,
		regtime,
		reg_ip,
		sec_primary,
		sec_content,
		Birthday,
		Province,
		LastModification,
		Sec_act
	)
VALUES
	(
		@JID,
		@StrUserID,
		@Password,
		@SecPassword,
		@Question,
		@Answer,
		@FullName,
		@Email,
		@Sex,
		@cid,
		@Address,
		@Phone,
		@Mobile,
		1,
		getDate(),
		@RegIP,
		3,
		3,
		@Birthday,
		@Province,
		getDate(),
		'ongate'
	) COMMIT TRANSACTION RETURN
END
else begin return -1
end